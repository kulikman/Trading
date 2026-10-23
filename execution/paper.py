"""Paper-сделки (часть T17, запуск по решению заказчика 15.10.2026) — без брокера и допов.

Вход ENTERED получает карточку PLANNED в момент решения. Вечерний прогон архива ведёт её до
выхода тем же расчётом, что тень (`learning.shadow`): цены входа и выхода — из архива по правилам
конструкции (стрэддл и кондор — вход по закрытию накануне реакции, выход до 11:00; режим C —
трейлинг до 20 дней). Переходы — по машине состояний SPEC §11: PLANNED → ARMED → OPEN →
CLOSING → CLOSED, или OPEN → STOPPED; ноги, исполнения и правило стопа — в карточке. P&L — в $
при риске сделки (доля капитала из шага решения). Цен нет за окно повтора — CANCELLED с причиной.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time
from decimal import Decimal
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.massive.history import EventDays
from backtest.mode_c import Entry
from backtest.simulate import Trade
from core.config.thresholds import Thresholds
from core.db import models as orm
from core.domain.trading import CardFill, CardStop
from core.registry.agent_jobs import REPORT_TIMES
from core.session_guard import ET
from core.state_machine.card import transition
from execution.attribution import attribute
from execution.cards import entry_fills, exit_fills, legs_of
from learning.shadow import Shadow

logger = logging.getLogger(__name__)

ACTIVE = ("PLANNED", "ARMED", "OPEN")
STOP_REASONS = ("stop", "trail_stop")
OPTION_ENTRY = time(15, 30)  # вход опционов накануне реакции (SPEC §10: T−1 15:30–15:55)
STOCK_ENTRY = time(10, 45)  # режим C — решение в 10:45
ARCHIVE_TIME = time(18, 30)  # вечерний прогон архива
CLOSE_TIME = time(16, 0)  # вход опционов paper — по закрытию накануне реакции


def stop_rule(construction: str, thresholds: Thresholds) -> str:
    """Правило стопа позиции словами (SPEC §10; числа — thresholds.yaml)."""
    rules, a, c = thresholds.constructions, thresholds.modes.A, thresholds.modes.C
    return {
        "straddle": f"стоимость упала на {rules.straddle.stop_premium_loss:.0%} премии",
        "iron_condor": f"убыток {rules.iron_condor.stop_premium_multiple:g}× премии",
        "mode_a": f"{a.stop_atr_multiple:g} × ATR({a.atr_period})",
        "mode_c": f"трейлинг {c.trailing_atr_multiple:g} × ATR({c.atr_period})",
    }.get(construction, construction)


@dataclass
class PaperRunResult:
    counts: dict[str, int] = field(default_factory=dict)


class Evaluator(Protocol):
    def evaluate(
        self,
        session: Session,
        step: orm.DecisionStep,
        event: orm.Event,
        days: EventDays,
        today: date,
        fixed_entry: Entry | None = None,
    ) -> Shadow:
        """Результат предложения шага по правилам конструкции (fixed_entry — вход уже исполнен)."""


class Spots(Protocol):
    def at(self, ticker: str, moment: datetime) -> float | None:
        """Цена акции на момент."""

    def close(self, ticker: str, day: date) -> float | None:
        """Закрытие дня."""


class PaperBook:
    def __init__(
        self,
        calculator: Evaluator,
        thresholds: Thresholds,
        *,
        spots: Spots | None = None,
        rate: float = 0.0,
    ) -> None:
        self._spots = spots
        self._rate = rate
        self._calculator = calculator
        self._thresholds = thresholds

    def run(self, session: Session, today: date, retry_since: date) -> PaperRunResult:
        """Ведёт активные paper-карточки закрывшихся событий до выхода."""
        result = PaperRunResult()
        rows = session.execute(
            select(orm.TradeCard, orm.Decision, orm.Event)
            .join(orm.Decision, orm.Decision.id == orm.TradeCard.decision_id)
            .join(orm.Event, orm.Event.id == orm.Decision.event_id)
            .where(orm.TradeCard.paper.is_(True), orm.TradeCard.state.in_(ACTIVE))
            .order_by(orm.TradeCard.id)
        ).all()
        for card, decision, event in rows:
            days = EventDays.of(event.report_date, REPORT_TIMES.get(event.report_time or ""))
            step = entry_step(session, decision)
            if days.reaction >= today or step is None:
                continue
            fixed = _filled_entry(card, decision)
            outcome = (
                self._calculator.evaluate(session, step, event, days, today)
                if fixed is None
                else self._calculator.evaluate(session, step, event, days, today, fixed_entry=fixed)
            )
            state = self._apply(session, card, step, outcome, days, today, retry_since)
            if card.state in ("CLOSED", "STOPPED") and outcome.trade is not None:
                self._attribute(
                    card,
                    event.ticker,
                    outcome.trade,
                    risk_scale(step, outcome.trade, self._thresholds),
                )
            result.counts[state] = result.counts.get(state, 0) + 1
        session.commit()
        logger.info("paper trades", extra={"counts": result.counts})
        return result

    def _apply(
        self,
        session: Session,
        card: orm.TradeCard,
        step: orm.DecisionStep,
        outcome: Shadow,
        days: EventDays,
        today: date,
        retry_since: date,
    ) -> str:
        trade, status = outcome.trade, outcome.status
        if trade is None:
            if status == "no_data" and days.reaction < retry_since and card.state == "PLANNED":
                at = datetime.combine(today, ARCHIVE_TIME, tzinfo=ET)
                transition(
                    session, card, "CANCELLED", at, outcome.note or "нет цен", check_session=False
                )
            return card.state
        risk_usd = self._thresholds.capital.module_usd * (step.risk_fraction or 0.0)
        scale = risk_scale(step, trade, self._thresholds)
        if card.state == "PLANNED" and trade.entry_on is not None:
            entry_time = STOCK_ENTRY if trade.construction in ("mode_c", "mode_a") else OPTION_ENTRY
            # акция режима C — фактическая минута исполнения из баров; константа — только там,
            # где времени исполнения нет (опционы по закрытию накануне, режим A)
            at = trade.entry_at or datetime.combine(trade.entry_on, entry_time, tzinfo=ET)
            transition(session, card, "ARMED", at, "ордер на вход", check_session=False)
            transition(session, card, "OPEN", at, "вход", check_session=False)
            card.legs = [leg.model_dump(mode="json") for leg in legs_of(trade, scale)]
            card.fills = [f.model_dump(mode="json") for f in entry_fills(trade, scale, at)]
            card.stop = CardStop(rule=stop_rule(trade.construction, self._thresholds)).model_dump(
                mode="json"
            )
        if status != "closed":
            return card.state
        card.pnl_total = Decimal(str(round(trade.return_on_risk * risk_usd, 2)))
        card.costs = Decimal(str(round(trade.costs * scale, 4)))
        held = {f["symbol"]: f["quantity"] for f in card.fills or [] if f.get("purpose") == "entry"}
        exits = [f.model_dump(mode="json") for f in exit_fills(trade, scale)]
        for fill in exits:  # выходим тем количеством, которым вошли (целые акции плана)
            fill["quantity"] = held.get(fill["symbol"], fill["quantity"])
        card.fills = [*(card.fills or []), *exits]
        if trade.exit_reason in STOP_REASONS:
            transition(
                session, card, "STOPPED", trade.exit_at, trade.exit_reason, check_session=False
            )
        else:
            transition(
                session, card, "CLOSING", trade.exit_at, "ордер на выход", check_session=False
            )
            transition(
                session, card, "CLOSED", trade.exit_at, trade.exit_reason, check_session=False
            )
        return card.state

    def _attribute(self, card: orm.TradeCard, ticker: str, trade: Trade, scale: float) -> None:
        """P&L по источникам (направление / волатильность / спад IV) для закрытой карточки."""
        is_option = any(leg.instrument == "option" for leg in trade.legs)
        spot_entry = spot_exit = None
        if is_option and self._spots is not None and trade.entry_on is not None:
            spot_entry = self._spots.close(ticker, trade.entry_on)
            spot_exit = self._spots.at(ticker, trade.exit_at)
        entry_at = datetime.combine(trade.entry_on or trade.exit_at.date(), CLOSE_TIME, tzinfo=ET)
        parts = attribute(
            trade.legs,
            scale=scale,
            spot_entry=spot_entry,
            spot_exit=spot_exit,
            entry_at=entry_at,
            exit_at=trade.exit_at,
            rate=self._rate,
        )
        if parts is None:
            logger.warning("no pnl attribution", extra={"card_id": card.id, "ticker": ticker})
            return
        card.pnl_direction = _money(parts.direction)
        card.pnl_vol = _money(parts.vol)
        card.pnl_ivcrush = _money(parts.ivcrush)


def _money(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))


def _filled_entry(card: orm.TradeCard, decision: orm.Decision) -> Entry | None:
    """Вход акции режима C, уже исполненный по барам (execution.paper_fill): цена и минута."""
    if decision.mode != "C" or card.state != "OPEN":
        return None
    for f in card.fills or []:
        if f.get("purpose") == "entry":
            fill = CardFill.model_validate(f, strict=False)
            return Entry(1 if fill.side == "buy" else -1, fill.price, fill.at)
    return None


def risk_scale(step: orm.DecisionStep, trade: Trade, thresholds: Thresholds) -> float:
    """Доля позиции бэктеста, дающая риск сделки (risk_fraction капитала)."""
    risk_usd = thresholds.capital.module_usd * (step.risk_fraction or 0.0)
    return risk_usd / trade.risk if trade.risk > 0 else 0.0


def entry_step(session: Session, decision: orm.Decision) -> orm.DecisionStep | None:
    """Шаг решения, давший вход: последнее прошедшее предложение стратегии по событию."""
    return session.scalars(
        select(orm.DecisionStep)
        .where(
            orm.DecisionStep.event_id == decision.event_id,
            orm.DecisionStep.strategy_id == decision.strategy_id,
            orm.DecisionStep.outcome == "proposal",
            orm.DecisionStep.is_shadow.is_(False),
        )
        .order_by(orm.DecisionStep.id.desc())
        .limit(1)
    ).first()
