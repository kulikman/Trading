"""«Сегодня», «Неделя», «Журнал», «Изменилось» (DASHBOARD.md §4.1, §4.2, §4.4).

Решения пишет модуль решений (T16). До него у отчётов статус «ЖДЁМ», действий человека нет,
а топ недели пуст: отбор недели — функция T16, общая с понедельничным дайджестом (T18).
"""

from collections.abc import Sequence
from datetime import date, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from api.format import Num, count, day, empty, et_msk, money
from api.trades_data import OpenCard
from core.db import models as orm
from core.session_guard import to_et

DECISION_LABELS = {
    "ENTERED": "ВХОД",
    "SKIPPED": "ПРОПУСК",
    "CANCELLED": "ОТМЕНА",
    "DATA_FAIL": "СБОЙ ДАННЫХ",
}
WAITING = "ЖДЁМ"
HUMAN_JOBS = {  # моменты, где нужен человек у терминала (SPEC §8)
    "mode_b_entry": "вход режим B",
    "mode_a_exit": "выход режим A",
    "be_at_terminal": "быть у терминала",
    "stop_gap": "стоп-гэп",
    "mode_c_decision": "решение режима C",
    "close_positions": "закрытие позиций",
}
STATE_STEPS = {
    "ARMED": "ждём вход",
    "OPEN": "позиция открыта",
    "C_MODE": "трейлинг, пересчёт 16:05 ET",
    "CLOSING": "закрытие",
}
NO_EVENTS = "нет событий"


class ActionRow(BaseModel):
    time: str
    ticker: str
    action: str
    card_id: int | None = None


class NowBlock(BaseModel):
    is_action: bool
    rows: list[ActionRow] = []
    message: str | None = None


class ReportRow(BaseModel):
    ticker: str
    time: str
    decision: str
    mode: str
    reason: str


class PositionRow(BaseModel):
    card_id: int
    ticker: str
    mode: str
    pnl: Num
    stop: Num
    next_step: str


class Today(BaseModel):
    now: NowBlock
    reports: list[ReportRow]
    reports_message: str | None
    positions: list[PositionRow]
    positions_message: str | None


class WeekEventRow(BaseModel):
    ticker: str
    date: str
    status: str
    reason: str


class Week(BaseModel):
    top: list[dict[str, str]]
    top_message: str | None
    events: list[WeekEventRow]
    events_message: str | None


class TerminalRow(BaseModel):
    day: str
    time: str
    ticker: str
    action: str


class Terminal(BaseModel):
    rows: list[TerminalRow]
    message: str | None


class JournalRow(BaseModel):
    date: str
    ticker: str
    status: str
    reasons: str
    shadow_result: Num


class ReasonRow(BaseModel):
    code: str
    times: Num
    saved: Num
    missed: Num


class Journal(BaseModel):
    summary: str
    reasons: list[ReasonRow]
    rows: list[JournalRow]
    message: str | None


class ChangeRow(BaseModel):
    time: str
    text: str


class Changes(BaseModel):
    rows: list[ChangeRow]


def today_view(session: Session, now: datetime, cards: Sequence[OpenCard]) -> Today:
    today = to_et(now).date()
    actions = _human_jobs(session, today, today + timedelta(days=1), entered_only=True)
    now_block = (
        NowBlock(
            is_action=True,
            rows=[
                ActionRow(time=et_msk(j.run_at), ticker=t, action=HUMAN_JOBS[j.job])
                for j, t in actions
            ],
        )
        if actions
        else NowBlock(is_action=False, message=_next_message(session, now))
    )
    reports = [
        ReportRow(
            ticker=e.ticker,
            time=e.report_time or "—",
            decision=DECISION_LABELS.get(d.status, WAITING) if d else WAITING,
            mode=(d.mode if d and d.mode else "—"),
            reason=(", ".join(d.reasons) if d and d.reasons else "—"),
        )
        for e, d in _events(session, today, today)
    ]
    positions = [
        PositionRow(
            card_id=c.card_id,
            ticker=c.ticker,
            mode=c.mode or "—",
            pnl=empty("нет данных до исполнителя (T17)"),
            stop=empty("нет данных до исполнителя (T17)"),
            next_step=STATE_STEPS.get(c.state, c.state),
        )
        for c in cards
    ]
    return Today(
        now=now_block,
        reports=reports,
        reports_message=None if reports else NO_EVENTS,
        positions=positions,
        positions_message=None if positions else "нет открытых позиций",
    )


def week_view(session: Session, now: datetime) -> Week:
    monday, friday = _week(now)
    events = [
        WeekEventRow(
            ticker=e.ticker,
            date=f"{day(e.report_date)} {e.report_time or ''}".strip(),
            status=(
                DECISION_LABELS.get(d.status, WAITING)
                if d
                else ("дата подтверждена" if e.date_status == "confirmed" else "дата — прогноз")
            ),
            reason=(", ".join(d.reasons) if d and d.reasons else "—"),
        )
        for e, d in _one_per_event(_events(session, monday, friday))
    ]
    return Week(
        top=[],
        top_message="Отбор недели появится с модулем решений (T16)",
        events=events,
        events_message=None if events else NO_EVENTS,
    )


def terminal_view(session: Session, now: datetime) -> Terminal:
    monday, friday = _week(now)
    rows = [
        TerminalRow(
            day=day(to_et(job.run_at).date()),
            time=et_msk(job.run_at),
            ticker=ticker,
            action=HUMAN_JOBS[job.job],
        )
        for job, ticker in _human_jobs(
            session, monday, friday + timedelta(days=1), entered_only=True
        )
    ]
    return Terminal(rows=rows, message=None if rows else "Действий человека на неделе нет")


def journal_view(session: Session, now: datetime, filter_: str) -> Journal:
    today = to_et(now).date()
    query = (
        select(orm.Event, orm.Decision)
        .join(orm.Decision, orm.Decision.event_id == orm.Event.id)
        .where(orm.Event.report_date <= today)
        .order_by(orm.Event.report_date.desc(), orm.Event.ticker)
    )
    pairs = session.execute(query).all()
    skipped = [(e, d) for e, d in pairs if d.status != "ENTERED"]
    saved, missed = 0.0, 0.0
    by_code: dict[str, list[float]] = {}
    for _, d in skipped:
        result = _shadow_pnl(d)
        for code in d.reasons or ["—"]:
            stats = by_code.setdefault(code, [0.0, 0.0, 0.0])
            stats[0] += 1
            if result is not None:
                stats[1] += max(-result, 0.0)
                stats[2] += max(result, 0.0)
        if result is not None:
            saved += max(-result, 0.0)
            missed += max(result, 0.0)
    chosen = {
        "all": pairs,
        "entered": [(e, d) for e, d in pairs if d.status == "ENTERED"],
        "skipped": skipped,
    }[filter_]
    rows = [
        JournalRow(
            date=day(e.report_date),
            ticker=e.ticker,
            status=d.status,
            reasons=", ".join(d.reasons) or "—",
            shadow_result=(
                money(_shadow_pnl(d), signed=True) if d.status != "ENTERED" else empty("—")
            ),
        )
        for e, d in chosen
    ]
    summary = (
        f"Пропуски сэкономили {money(saved).display} · упустили {money(missed).display}"
        if skipped
        else "Пропусков ещё нет"
    )
    return Journal(
        summary=summary,
        reasons=[
            ReasonRow(code=code, times=count(int(n)), saved=money(s), missed=money(m))
            for code, (n, s, m) in sorted(by_code.items())
        ],
        rows=rows,
        message=None if rows else "решений ещё нет",
    )


def changes_view(session: Session, since: datetime, limit: int = 5) -> Changes:
    rows = session.execute(
        select(orm.EventChange, orm.Event.ticker)
        .join(orm.Event, orm.Event.id == orm.EventChange.event_id)
        .where(orm.EventChange.at > since)
        .order_by(orm.EventChange.at.desc())
        .limit(limit)
    ).all()
    return Changes(
        rows=[ChangeRow(time=et_msk(c.at), text=_change_text(c, ticker)) for c, ticker in rows]
    )


def _change_text(change: orm.EventChange, ticker: str) -> str:
    field = {
        "report_date": "дата отчёта",
        "report_time": "время отчёта",
        "date_status": "статус даты",
        "fiscal_period": "фискальный период",
        "date_check": "сверка даты",
    }.get(change.field, change.field)
    text = f"{ticker}: {field} {change.old_value or '—'} → {change.new_value or '—'}"
    return f"{text} ({change.reason})" if change.reason else text


def _events(
    session: Session, first: date, last: date
) -> list[tuple[orm.Event, orm.Decision | None]]:
    rows = session.execute(
        select(orm.Event, orm.Decision)
        .outerjoin(orm.Decision, orm.Decision.event_id == orm.Event.id)
        .where(orm.Event.report_date >= first, orm.Event.report_date <= last)
        .order_by(orm.Event.report_date, orm.Event.report_time, orm.Event.ticker, orm.Decision.id)
    ).all()
    return [(e, d) for e, d in rows]


def _one_per_event(
    rows: list[tuple[orm.Event, orm.Decision | None]],
) -> list[tuple[orm.Event, orm.Decision | None]]:
    """Одна строка на событие. У события либо один SKIPPED, либо только входы — берётся первый."""
    out: dict[int, tuple[orm.Event, orm.Decision | None]] = {}
    for event, decision in rows:
        out.setdefault(event.id, (event, decision))
    return list(out.values())


def _human_jobs(
    session: Session, first: date, before: date, *, entered_only: bool
) -> list[tuple[orm.EventJob, str]]:
    """Задачи, где нужен человек, в окне дат ET; только у событий с решением ВХОД."""
    query = (
        select(orm.EventJob, orm.Event.ticker)
        .join(orm.Event, orm.Event.id == orm.EventJob.event_id)
        .where(orm.EventJob.job.in_(HUMAN_JOBS), orm.EventJob.status == "planned")
        .order_by(orm.EventJob.run_at)
    )
    if entered_only:
        query = query.where(
            exists().where(orm.Decision.event_id == orm.Event.id, orm.Decision.status == "ENTERED")
        )
    return [
        (job, ticker)
        for job, ticker in session.execute(query).all()
        if first <= to_et(job.run_at).date() < before
    ]


def _next_message(session: Session, now: datetime) -> str:
    upcoming = [
        (job, ticker)
        for job, ticker in _human_jobs(session, to_et(now).date(), date.max, entered_only=True)
        if job.run_at > now
    ]
    if upcoming:
        job, ticker = upcoming[0]
        return f"Действий нет. Следующее: {et_msk(job.run_at)} — {HUMAN_JOBS[job.job]} {ticker}"
    event = session.scalars(
        select(orm.Event)
        .where(orm.Event.report_date >= to_et(now).date())
        .order_by(orm.Event.report_date, orm.Event.ticker)
        .limit(1)
    ).first()
    if event is None:
        return "Действий нет."
    return f"Действий нет. Ближайший отчёт: {event.ticker} {day(event.report_date)}"


def _week(now: datetime) -> tuple[date, date]:
    today = to_et(now).date()
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=4)


def _shadow_pnl(decision: orm.Decision) -> float | None:
    """Итог теневой сделки пропуска, $ (поле `pnl` в decision.shadow — пишет T16)."""
    shadow = decision.shadow
    if isinstance(shadow, dict):
        value = shadow.get("pnl")
        if isinstance(value, int | float):
            return float(value)
    return None
