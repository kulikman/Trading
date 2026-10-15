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
from core.config.thresholds import Thresholds
from core.db import models as orm
from core.domain.trading import CardStop
from core.registry.agent_jobs import REPORT_TIMES
from core.session_guard import ET
from core.state_machine.card import transition
from execution.cards import entry_fills, exit_fills, legs_of
from learning.shadow import Shadow

logger = logging.getLogger(__name__)

ACTIVE = ("PLANNED", "ARMED", "OPEN")
STOP_REASONS = ("stop", "trail_stop")
OPTION_ENTRY = time(15, 30)  # вход опционов накануне реакции (SPEC §10: T−1 15:30–15:55)
STOCK_ENTRY = time(10, 45)  # режим C — решение в 10:45
ARCHIVE_TIME = time(18, 30)  # вечерний прогон архива


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
    ) -> Shadow:
        """Результат предложения шага по правилам конструкции."""


class PaperBook:
    def __init__(self, calculator: Evaluator, thresholds: Thresholds) -> None:
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
            step = _entry_step(session, decision)
            if days.reaction >= today or step is None:
                continue
            outcome = self._calculator.evaluate(session, step, event, days, today)
            state = self._apply(session, card, step, outcome, days, today, retry_since)
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
        scale = risk_usd / trade.risk if trade.risk > 0 else 0.0
        if card.state == "PLANNED" and trade.entry_on is not None:
            entry_time = STOCK_ENTRY if trade.construction in ("mode_c", "mode_a") else OPTION_ENTRY
            at = datetime.combine(trade.entry_on, entry_time, tzinfo=ET)
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
        card.fills = [
            *(card.fills or []),
            *(f.model_dump(mode="json") for f in exit_fills(trade, scale)),
        ]
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


def _entry_step(session: Session, decision: orm.Decision) -> orm.DecisionStep | None:
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
