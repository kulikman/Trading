"""Сообщение «ДЕЙСТВИЕ» о новом paper-входе (SPEC §12; минимум для запуска 15.10.2026).

Одна карточка — одно сообщение: отправленное помечается tg_message_id и не повторяется. Без кнопок
и правок сообщения — paper; это добавит T18. Время — ET и МСК.
"""

from datetime import date, datetime, time
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.massive.history import EventDays
from core.config.thresholds import Thresholds
from core.db import models as orm
from core.registry.agent_jobs import REPORT_TIMES
from core.session_guard import ET, to_et

MSK = ZoneInfo("Europe/Moscow")
REPORT_WORDS = {"BMO": "до открытия", "AMC": "после закрытия", "DURING": "во время сессии"}
NAMES = {
    "straddle": "стрэддл",
    "iron_condor": "iron condor",
    "stock": "акция",
    "stock_short": "акция, продажа",
}


class Sender(Protocol):
    def send(self, text: str) -> int:
        """Отправить сообщение; вернуть его id."""


def signal_text(
    event: orm.Event, decision: orm.Decision, risk_fraction: float, thresholds: Thresholds
) -> str:
    """Текст сообщения о входе: что, когда войти, когда выйти, сколько под риском."""
    days = EventDays.of(event.report_date, REPORT_TIMES.get(event.report_time or ""))
    construction = decision.construction or ""
    when = REPORT_WORDS.get(event.report_time or "", "время не подтверждено")
    risk_usd = thresholds.capital.module_usd * risk_fraction
    name = NAMES.get(construction, construction)
    lines = [f"{event.ticker} · отчёт {_day(event.report_date)} {when} · {name} · PAPER"]
    if construction in ("straddle", "iron_condor"):
        straddle, condor = thresholds.constructions.straddle, thresholds.constructions.iron_condor
        exit_rule = (
            f"стоп −{straddle.stop_premium_loss:.0%} премии, "
            f"цель +{straddle.target_premium_gain:.0%}"
            if construction == "straddle"
            else f"стоп {condor.stop_premium_multiple:g}× премии, "
            f"цель {condor.target_premium_share:.0%}"
        )
        lines += [
            f"ВХОД   {_at(days.pre, time(15, 30))}, по закрытию",
            f"ВЫХОД  {_at(days.reaction, time(11, 0))} — не позже; {exit_rule}",
        ]
    else:
        c = thresholds.modes.C
        limit = f"лимит — VWAP первого часа ± {c.max_entry_over_vwap:.1%}, до 11:00 ET"
        trail = f"трейлинг {c.trailing_atr_multiple:g} × ATR({c.atr_period})"
        rest = f"закрытие хуже SMA({c.exit_sma_period}), не дольше {c.max_hold_days} дней"
        lines += [
            f"ВХОД   {_at(days.reaction, time(10, 45))}, {limit}",
            f"ВЫХОД  {trail}, {rest}",
        ]
    lines.append(f"РИСК   {risk_fraction:.1%} капитала — ${risk_usd:,.0f}".replace(",", " "))
    return "\n".join(lines)


def send_new_signals(session: Session, client: Sender, thresholds: Thresholds) -> int:
    """Отправить сообщения по новым paper-входам; вернуть число отправленных."""
    rows = session.execute(
        select(orm.TradeCard, orm.Decision, orm.Event)
        .join(orm.Decision, orm.Decision.id == orm.TradeCard.decision_id)
        .join(orm.Event, orm.Event.id == orm.Decision.event_id)
        .where(orm.TradeCard.paper.is_(True), orm.TradeCard.tg_message_id.is_(None))
        .where(orm.TradeCard.state.in_(("PLANNED", "OPEN")))
        .order_by(orm.TradeCard.id)
    ).all()
    sent = 0
    for card, decision, event in rows:
        step = session.scalars(
            select(orm.DecisionStep.risk_fraction)
            .where(
                orm.DecisionStep.event_id == decision.event_id,
                orm.DecisionStep.strategy_id == decision.strategy_id,
                orm.DecisionStep.outcome == "proposal",
            )
            .order_by(orm.DecisionStep.id.desc())
            .limit(1)
        ).first()
        card.tg_message_id = client.send(signal_text(event, decision, step or 0.0, thresholds))
        session.commit()  # отправленное фиксируется сразу: сбой на следующей его не повторит
        sent += 1
    return sent


def _at(day: date, clock: time) -> str:
    moment = datetime.combine(day, clock, tzinfo=ET)
    return f"{_day(day)} {to_et(moment):%H:%M} ET ({moment.astimezone(MSK):%H:%M} МСК)"


def _day(value: date) -> str:
    return f"{value:%d.%m}"
