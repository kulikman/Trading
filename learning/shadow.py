"""Теневые сделки (T16, SPEC §10): результат предложений, которые не стали входом.

Решение заказчика 15.10.2026: тень считается по каждому предложению, которое не стало входом, —
отклонённые воротами и все предложения стратегий в стадии shadow (режимы A и B).
- стрэддл и кондор — бэктестом по архиву (вход по закрытию накануне реакции, выход до 11:00);
- режим A — длинная акция T−7 → T−1 по дневным свечам;
- режим C — правила бэктеста T12b (позиция может быть ещё открыта — пересчёт каждый вечер);
- режим B (коллар, пут-спред) — без P&L: Brier прогноза направления против факта (критерий
  перевода B в paper, SPEC §17); тень с опционами B — с исполнителем (T17).
P&L — в $ при риске sizing.data_collection_risk капитала. Считается в вечернем прогоне архива,
когда минутные цены опционов на выход уже скачаны. Итог SKIPPED получает лучшую отклонённую
конструкцию (`decision.shadow`, `earnings_track.shadow_pnl`) — её читает журнал дашборда.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from adapters.massive.history import EventDays, stock_closes
from adapters.massive.symbols import daily_bars, symbol_periods
from backtest.mode_a import mode_a_trade
from backtest.mode_c_run import StockData, stock_trade
from backtest.run import option_trade
from backtest.simulate import Trade
from core.config.sources import MassiveHistory
from core.config.thresholds import Thresholds
from core.db import models as orm
from core.domain.types import ShadowStatus
from core.registry.agent_jobs import REPORT_TIMES
from core.session_guard import to_et
from execution.costs import CostModel

logger = logging.getLogger(__name__)

DIRECTIONAL: dict[str, Literal[1, -1]] = {"stock_collar": 1, "put_spread": -1}  # режим B
HISTORY_DAYS = 60  # дневные свечи до входа: ATR(14) и объём
FINAL: tuple[ShadowStatus, ...] = ("closed", "scored")


@dataclass(frozen=True)
class Shadow:
    status: ShadowStatus
    note: str | None = None
    trade: Trade | None = None
    brier: float | None = None


@dataclass
class ShadowRunResult:
    counts: dict[str, int] = field(default_factory=dict)


def shadow_candidates(session: Session) -> list[orm.DecisionStep]:
    """Последнее предложение каждой стратегии по событию, если оно не стало входом."""
    latest: dict[tuple[int, str], orm.DecisionStep] = {}
    for step in session.scalars(
        select(orm.DecisionStep)
        .where(orm.DecisionStep.construction.is_not(None))
        .order_by(orm.DecisionStep.id)
    ):
        latest[(step.event_id, step.strategy_id)] = step
    entered = set(
        session.execute(
            select(orm.Decision.event_id, orm.Decision.strategy_id).where(
                orm.Decision.status == "ENTERED"
            )
        ).all()
    )
    return [step for key, step in latest.items() if key not in entered]


class ShadowCalculator:
    def __init__(
        self,
        *,
        stocks: StockData,
        thresholds: Thresholds,
        history: MassiveHistory,
        costs: CostModel,
    ) -> None:
        self._stocks = stocks
        self._thresholds = thresholds
        self._history = history
        self._costs = costs

    def run(self, session: Session, today: date, retry_since: date) -> ShadowRunResult:
        """Тени закрывшихся событий; no_data повторяется, пока реакция не старше retry_since."""
        result = ShadowRunResult()
        done = {
            (r.event_id, r.strategy_id): r.status for r in session.scalars(select(orm.ShadowTrade))
        }
        for step in shadow_candidates(session):
            status = done.get((step.event_id, step.strategy_id))
            event = session.get(orm.Event, step.event_id)
            if event is None or status in FINAL:
                continue
            days = EventDays.of(event.report_date, REPORT_TIMES.get(event.report_time or ""))
            if days.reaction >= today or (status == "no_data" and days.reaction < retry_since):
                continue
            shadow = self.evaluate(session, step, event, days, today)
            self._save(session, step, shadow)
            result.counts[shadow.status] = result.counts.get(shadow.status, 0) + 1
        mark_skipped_decisions(session)
        session.commit()
        logger.info("shadow trades", extra={"counts": result.counts})
        return result

    def evaluate(
        self,
        session: Session,
        step: orm.DecisionStep,
        event: orm.Event,
        days: EventDays,
        today: date,
    ) -> Shadow:
        """Результат предложения шага по правилам его конструкции (тень и paper-сделка)."""
        construction = step.construction or ""
        track = session.scalars(
            select(orm.EarningsTrack).where(
                orm.EarningsTrack.ticker == event.ticker,
                orm.EarningsTrack.report_date == event.report_date,
            )
        ).first()
        if construction in DIRECTIONAL:
            if track is None or track.actual_move is None or step.probability is None:
                return Shadow("no_data", "no_actual_move")
            hit = 1.0 if DIRECTIONAL[construction] * track.actual_move > 0 else 0.0
            return Shadow("scored", brier=(step.probability - hit) ** 2)
        if construction in ("straddle", "iron_condor"):
            if track is None or track.implied_move is None:
                return Shadow("no_data", "no_implied_move")
            closes = stock_closes(
                daily_bars(self._stocks, event.ticker, days.pre - timedelta(days=10), days.reaction)
            )
            return _of(
                option_trade(
                    session,
                    event.ticker,
                    days,
                    track.implied_move,
                    "straddle" if construction == "straddle" else "iron_condor",
                    closes,
                    thresholds=self._thresholds,
                    history=self._history,
                    costs=self._costs,
                    condor_stop=self._thresholds.constructions.iron_condor.stop_basis,
                )
            )
        if step.mode == "A":
            return self._mode_a(session, event)
        if step.mode == "C":
            daily = daily_bars(
                self._stocks, event.ticker, days.pre - timedelta(days=HISTORY_DAYS), today
            )
            return _of(
                stock_trade(
                    event.ticker,
                    days,
                    1 if construction == "stock" else -1,
                    daily,
                    stock_closes(daily),
                    symbol_periods(event.ticker, self._stocks.ticker_changes(event.ticker)),
                    self._stocks,
                    self._thresholds,
                    self._costs,
                    self._thresholds.capital.module_usd,
                )
            )
        return Shadow("no_data", f"no_simulator:{construction}")

    def _mode_a(self, session: Session, event: orm.Event) -> Shadow:
        entry, exit_ = (
            session.get(orm.EventJob, (event.id, stage, job))
            for stage, job in (("T-7", "mode_a_decision"), ("T-1", "mode_a_exit"))
        )
        if entry is None or exit_ is None:
            return Shadow("no_data", "no_schedule")
        entry_day, exit_day = to_et(entry.run_at).date(), to_et(exit_.run_at).date()
        daily = daily_bars(
            self._stocks, event.ticker, entry_day - timedelta(days=HISTORY_DAYS), exit_day
        )
        return _of(
            mode_a_trade(
                event.ticker,
                event.report_date,
                entry_day,
                exit_day,
                daily,
                thresholds=self._thresholds,
                costs=self._costs,
                capital=self._thresholds.capital.module_usd,
            )
        )

    def _save(self, session: Session, step: orm.DecisionStep, shadow: Shadow) -> None:
        trade = shadow.trade
        risk_usd = (
            self._thresholds.capital.module_usd * self._thresholds.sizing.data_collection_risk
        )
        values = {
            "step_id": step.id,
            "construction": step.construction,
            "status": shadow.status,
            "note": shadow.note,
            "entry_on": trade.entry_on if trade else None,
            "exit_at": trade.exit_at if trade else None,
            "exit_reason": trade.exit_reason if trade else None,
            "return_on_risk": trade.return_on_risk if trade else None,
            "pnl": trade.return_on_risk * risk_usd if trade else None,
            "brier": shadow.brier,
        }
        statement = insert(orm.ShadowTrade).values(
            event_id=step.event_id, strategy_id=step.strategy_id, **values
        )
        session.execute(
            statement.on_conflict_do_update(index_elements=["event_id", "strategy_id"], set_=values)
        )


def mark_skipped_decisions(session: Session) -> None:
    """Итог SKIPPED: лучшая отклонённая (не shadow) конструкция — по наибольшему edge."""
    rows = session.execute(
        select(orm.Decision, orm.ShadowTrade, orm.DecisionStep, orm.Event)
        .join(orm.ShadowTrade, orm.ShadowTrade.event_id == orm.Decision.event_id)
        .join(orm.DecisionStep, orm.DecisionStep.id == orm.ShadowTrade.step_id)
        .join(orm.Event, orm.Event.id == orm.Decision.event_id)
        .where(
            orm.Decision.status == "SKIPPED",
            orm.DecisionStep.is_shadow.is_(False),
            orm.ShadowTrade.pnl.is_not(None),
        )
    ).all()
    best: dict[int, tuple[orm.Decision, orm.ShadowTrade, orm.DecisionStep, orm.Event]] = {}
    for decision, shadow, step, event in rows:
        kept = best.get(decision.id)
        if kept is None or (step.edge or 0.0) > (kept[2].edge or 0.0):
            best[decision.id] = (decision, shadow, step, event)
    for decision, shadow, _, event in best.values():
        decision.shadow = {
            "strategy_id": shadow.strategy_id,
            "construction": shadow.construction,
            "pnl": shadow.pnl,
        }
        track = session.scalars(
            select(orm.EarningsTrack).where(
                orm.EarningsTrack.ticker == event.ticker,
                orm.EarningsTrack.report_date == event.report_date,
            )
        ).first()
        if track is not None and shadow.pnl is not None:
            track.shadow_pnl = Decimal(str(round(shadow.pnl, 4)))


def _of(outcome: Trade | str) -> Shadow:
    if isinstance(outcome, Trade):
        return Shadow("closed", trade=outcome)
    if outcome == "open_at_end":
        return Shadow("open", "open_at_end")
    return Shadow("no_data", outcome)
