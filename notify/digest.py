"""Дайджесты и «БЫТЬ У ТЕРМИНАЛА» (SPEC §12, T18). Время — ET и МСК.

ДАЙДЖЕСТ (без звука): утро 08:30 ET — отчёты дня, открытые позиции, закрытия прошлого торгового
дня; в понедельник ещё события недели (без рейтинга — отбор недели E2d отложен, решение заказчика
15.10.2026) и итог прошлой недели. Вечер 16:30 ET — закрытия дня, отчёты завтра и входы под них,
открытые позиции («вечерний дайджест + план» T−1 покрывается им).
БЫТЬ У ТЕРМИНАЛА (со звуком, T0 09:00): только при Real-входе — у paper действий человека нет.
"""

from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from adapters.massive.history import EventDays
from core.config.thresholds import Thresholds
from core.db import models as orm
from core.domain.schedule import EventJob
from core.registry.agent_jobs import REPORT_TIMES
from core.scheduler.dispatch import Handler
from core.session_guard import ET, next_trading_day, previous_trading_day, to_et
from decision.week import WeekSelection, select_week
from notify.signals import NAMES, REPORT_WORDS

MSK = ZoneInfo("Europe/Moscow")
OPEN_STATES = ("OPEN", "C_MODE", "CLOSING")
CLOSED_STATES = ("CLOSED", "STOPPED")
STATUS_WORDS = {
    "ENTERED": "вход",
    "SKIPPED": "пропуск",
    "CANCELLED": "отменено",
    "DATA_FAIL": "сбой данных",
}


class Messenger(Protocol):
    def send(self, text: str, *, silent: bool = False) -> int:
        """Отправить сообщение; вернуть его id."""


def morning_text(session: Session, now: datetime, thresholds: Thresholds) -> str:
    """Утренний дайджест 08:30 ET; в понедельник — отбор недели (decision.week)."""
    today = to_et(now).date()
    lines = [_header("ДАЙДЖЕСТ · утро", now)]
    lines += _section("Отчёты сегодня", _reports(session, today, today))
    lines += _section("Открытые позиции", _open_positions(session))
    yesterday = previous_trading_day(today)
    lines += _section(f"Закрыто {yesterday:%d.%m}", _closed(session, yesterday, yesterday))
    if today.weekday() == 0:
        selection = select_week(session, today, thresholds)
        lines += _section(
            f"Неделя {selection.first:%d.%m}–{selection.last:%d.%m}", _week_lines(selection)
        )
        last_monday = today - timedelta(days=7)
        lines += _section("Итог прошлой недели", [_week_total(session, last_monday)])
    return "\n".join(lines)


def evening_text(session: Session, now: datetime) -> str:
    """Вечерний дайджест 16:30 ET: итоги дня и план на завтра."""
    today = to_et(now).date()
    tomorrow = next_trading_day(today)
    lines = [_header("ДАЙДЖЕСТ · вечер", now)]
    lines += _section("Закрыто сегодня", _closed(session, today, today))
    lines += _section(f"Отчёты {tomorrow:%d.%m}", _reports(session, tomorrow, tomorrow))
    lines += _section("Открытые позиции", _open_positions(session))
    return "\n".join(lines)


def terminal_text(session: Session, event: orm.Event) -> str | None:
    """«БЫТЬ У ТЕРМИНАЛА» по Real-входам события; у paper — None (действий человека нет)."""
    real = session.scalars(
        select(orm.Decision.construction)
        .join(orm.TradeCard, orm.TradeCard.decision_id == orm.Decision.id)
        .where(orm.Decision.event_id == event.id, orm.TradeCard.paper.is_(False))
        .where(orm.TradeCard.state.in_(("ARMED", *OPEN_STATES)))
    ).all()
    if not real:
        return None
    names = ", ".join(NAMES.get(c or "", c or "") for c in real)
    reaction = EventDays.of(event.report_date, REPORT_TIMES.get(event.report_time or "")).reaction
    opening = datetime.combine(reaction, time(9, 30), tzinfo=ET)
    when = f"{opening:%d.%m} 09:30 ET ({opening.astimezone(MSK):%H:%M} МСК)"
    plan = "стоп-гэп на открытии, выходы до 11:00"
    return f"БЫТЬ У ТЕРМИНАЛА · {event.ticker} · {names}\n{when}: {plan}"


def notify_handlers(client_factory: Callable[[], Messenger | None]) -> dict[str, Handler]:
    """Задачи событий kind=notify: «быть у терминала» и вечерний дайджест T−1 (общий в 16:30)."""

    def terminal(session: Session, job: EventJob) -> None:
        event = session.get(orm.Event, job.event_id)
        client = client_factory()
        text = None if event is None else terminal_text(session, event)
        if client is not None and text is not None:
            client.send(text)

    def evening(session: Session, job: EventJob) -> None:
        """Покрывается общим вечерним дайджестом 16:30 ET — отдельного сообщения нет."""

    return {"be_at_terminal": terminal, "evening_digest": evening}


def _header(title: str, now: datetime) -> str:
    et = to_et(now)
    return f"{title} · {et:%d.%m} {et:%H:%M} ET ({now.astimezone(MSK):%H:%M} МСК)"


def _section(title: str, rows: list[str]) -> list[str]:
    return ["", f"{title}:", *(rows or ["—"])]


def _reports(session: Session, first: date, last: date) -> list[str]:
    rows = session.execute(
        select(orm.Event, orm.Decision.status)
        .outerjoin(orm.Decision, orm.Decision.event_id == orm.Event.id)
        .where(orm.Event.report_date >= first, orm.Event.report_date <= last)
        .order_by(orm.Event.report_date, orm.Event.ticker)
    ).all()
    seen: dict[int, str] = {}
    for event, status in rows:
        when = REPORT_WORDS.get(event.report_time or "", "время ?")
        state = STATUS_WORDS.get(status or "", "ждём решения")
        if event.id not in seen or status == "ENTERED":
            seen[event.id] = f"{event.report_date:%d.%m} {event.ticker} · {when} · {state}"
    return list(seen.values())


def _week_lines(selection: WeekSelection) -> list[str]:
    """Отбор недели — тот же список и порядок, что на экране «Неделя» (SPEC §17 п.2)."""
    lines = []
    for n, pick in enumerate(selection.top, start=1):
        name = NAMES.get(pick.construction or "", pick.construction or "—")
        expected = pick.expected_usd or 0.0
        sign = "+" if expected >= 0 else "−"
        lines.append(
            f"{n}. {pick.event.report_date:%d.%m} {pick.event.ticker} · {name} · "
            f"ожидаемая прибыль {sign}${abs(expected):,.0f}".replace(",", " ")
        )
    for pick in selection.rest:
        when = REPORT_WORDS.get(pick.event.report_time or "", "время ?")
        state = STATUS_WORDS.get(pick.decision.status if pick.decision else "", "ждём решения")
        lines.append(f"{pick.event.report_date:%d.%m} {pick.event.ticker} · {when} · {state}")
    return lines


def _open_positions(session: Session) -> list[str]:
    rows = session.execute(
        select(orm.TradeCard, orm.Decision, orm.Event)
        .join(orm.Decision, orm.Decision.id == orm.TradeCard.decision_id)
        .join(orm.Event, orm.Event.id == orm.Decision.event_id)
        .where(orm.TradeCard.state.in_(OPEN_STATES))
        .order_by(orm.TradeCard.id)
    ).all()
    out = []
    for card, decision, event in rows:
        name = NAMES.get(decision.construction or "", decision.construction or "")
        stop = (card.trailing or {}).get("stop")
        kind = "PAPER" if card.paper else "REAL"
        out.append(f"{event.ticker} · {name} · {kind}" + (f" · стоп {stop:.2f}" if stop else ""))
    return out


def _closed(session: Session, first: date, last: date) -> list[str]:
    start, end = _bounds(first, last)
    rows = session.execute(
        select(orm.TradeCard, orm.Decision, orm.Event, orm.TradeCardTransition.reason)
        .join(orm.Decision, orm.Decision.id == orm.TradeCard.decision_id)
        .join(orm.Event, orm.Event.id == orm.Decision.event_id)
        .join(orm.TradeCardTransition, orm.TradeCardTransition.card_id == orm.TradeCard.id)
        .where(
            orm.TradeCardTransition.to_state.in_(CLOSED_STATES),
            orm.TradeCardTransition.at >= start,
            orm.TradeCardTransition.at < end,
        )
        .order_by(orm.TradeCardTransition.at)
    ).all()
    out = []
    for card, decision, event, reason in rows:
        name = NAMES.get(decision.construction or "", decision.construction or "")
        pnl = float(card.pnl_total or 0)
        out.append(
            f"{event.ticker} · {name} · {reason or ''} · {_money(pnl)}".replace(" ·  ·", " ·")
        )
    return out


def _week_total(session: Session, monday: date) -> str:
    start, end = _bounds(monday, monday + timedelta(days=4))
    closed = (
        select(orm.TradeCardTransition.card_id)
        .where(
            orm.TradeCardTransition.to_state.in_(CLOSED_STATES),
            orm.TradeCardTransition.at >= start,
            orm.TradeCardTransition.at < end,
        )
        .subquery()
    )
    count, total = session.execute(
        select(
            func.count(orm.TradeCard.id), func.coalesce(func.sum(orm.TradeCard.pnl_total), 0)
        ).where(orm.TradeCard.id.in_(select(closed.c.card_id)), orm.TradeCard.paper.is_(True))
    ).one()
    return f"PAPER: сделок {count}, итог {_money(float(total or 0))}"


def _bounds(first: date, last: date) -> tuple[datetime, datetime]:
    """[начало first; начало дня после last) в ET."""
    start = datetime.combine(first, datetime.min.time(), tzinfo=ET)
    end = datetime.combine(last + timedelta(days=1), datetime.min.time(), tzinfo=ET)
    return start, end


def _money(value: float) -> str:
    sign = "+" if value >= 0 else "−"
    return f"{sign}${abs(value):,.0f}".replace(",", " ")
