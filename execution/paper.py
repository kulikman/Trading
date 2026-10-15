"""Paper-сделки (часть T17, запуск по решению заказчика 15.10.2026) — без брокера и допов.

Вход ENTERED получает карточку PLANNED в момент решения. Вечерний прогон архива ведёт её до
выхода тем же расчётом, что тень (`learning.shadow`): цены входа и выхода — из архива по правилам
конструкции (стрэддл и кондор — вход по закрытию накануне реакции, выход до 11:00; режим C —
трейлинг до 20 дней). PLANNED → OPEN → CLOSED / STOPPED; P&L — в $ при риске сделки
(доля капитала из шага решения). Цен так и нет за окно повтора — CANCELLED с причиной.
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
from core.registry.agent_jobs import REPORT_TIMES
from core.session_guard import ET
from execution.cards import move
from learning.shadow import Shadow

logger = logging.getLogger(__name__)

ACTIVE = ("PLANNED", "OPEN")
STOP_REASONS = ("stop", "trail_stop")
OPTION_ENTRY = time(15, 30)  # вход опционов накануне реакции (SPEC §10: T−1 15:30–15:55)
STOCK_ENTRY = time(10, 45)  # режим C — решение в 10:45
ARCHIVE_TIME = time(18, 30)  # вечерний прогон архива


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
            if status == "no_data" and days.reaction < retry_since:
                at = datetime.combine(today, ARCHIVE_TIME, tzinfo=ET)
                move(session, card, "CANCELLED", at, outcome.note or "нет цен")
            return card.state
        entry_time = STOCK_ENTRY if trade.construction in ("mode_c", "mode_a") else OPTION_ENTRY
        if card.state == "PLANNED" and trade.entry_on is not None:
            move(
                session,
                card,
                "OPEN",
                datetime.combine(trade.entry_on, entry_time, tzinfo=ET),
                "вход",
            )
        card.fills = {
            "entry": trade.entry_value,
            "exit": trade.exit_value if status == "closed" else None,
        }
        if status != "closed":
            return card.state
        risk_usd = self._thresholds.capital.module_usd * (step.risk_fraction or 0.0)
        card.pnl_total = Decimal(str(round(trade.return_on_risk * risk_usd, 2)))
        final = "STOPPED" if trade.exit_reason in STOP_REASONS else "CLOSED"
        move(session, card, final, trade.exit_at, trade.exit_reason)
        return final


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
