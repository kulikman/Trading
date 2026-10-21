from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from adapters.alphavantage.models import AvCalendarRow
from adapters.errors import DataError
from adapters.finnhub.models import FinnhubEarning
from agents.calendar.agent import CalendarAgent
from core.config import load_config
from core.db import models as orm

AS_OF = date(2026, 10, 13)
NOW = datetime(2026, 10, 13, 10, 0, tzinfo=UTC)
CONFIG = load_config()
JOBS_PER_EVENT = len(CONFIG.schedule.event_jobs)


def fh(symbol: str, day: str, hour: str = "bmo", quarter: int = 3) -> FinnhubEarning:
    return FinnhubEarning.model_validate(
        {
            "symbol": symbol,
            "date": day,
            "hour": hour,
            "year": 2026,
            "quarter": quarter,
            "epsEstimate": 1.0,
            "revenueEstimate": 1e9,
        }
    )


def av(symbol: str, day: str, time_of_day: str = "pre-market") -> AvCalendarRow:
    return AvCalendarRow.model_validate(
        {
            "symbol": symbol,
            "name": symbol,
            "reportDate": day,
            "fiscalDateEnding": "2026-09-30",
            "estimate": "1.0",
            "currency": "USD",
            "timeOfTheDay": time_of_day,
        }
    )


class Source:
    def __init__(self, rows: list[Any] | Exception) -> None:
        self.rows = rows
        self.calls = 0

    def earnings_calendar(self, *args: Any, **kwargs: Any) -> list[Any]:
        self.calls += 1
        if isinstance(self.rows, Exception):
            raise self.rows
        return list(self.rows)


class Notifier:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str | None]] = []

    def system(self, text: str, *, code: str | None = None) -> None:
        self.messages.append((text, code))


def agent(finnhub: Source, alphavantage: Source, notifier: Notifier) -> CalendarAgent:
    return CalendarAgent(
        finnhub=finnhub,
        alphavantage=alphavantage,
        notifier=notifier,
        universe=CONFIG.universe,
        schedule=CONFIG.schedule,
    )


def count(session: Session, model: Any) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


def events(session: Session) -> dict[str, orm.Event]:
    return {e.ticker: e for e in session.scalars(select(orm.Event)).all()}


FINNHUB = [
    fh("GS", "2026-10-20"),
    fh("MS", "2026-10-21"),
    fh("NFLX", "2026-10-22", "amc"),
    fh("ZZZZ", "2026-10-22"),
]
ALPHAVANTAGE = [
    av("GS", "2026-10-20"),
    av("MS", "2026-10-22"),
    av("AAPL", "2026-10-29", "post-market"),
]


def test_first_run_creates_events_jobs_and_flags_mismatch(session: Session) -> None:
    notifier = Notifier()
    result = agent(Source(FINNHUB), Source(ALPHAVANTAGE), notifier).run(
        session, as_of=AS_OF, now=NOW
    )
    assert sorted(result.created) == ["GS", "MS", "NFLX"]  # ZZZZ — не из вселенной
    assert result.mismatches == ["MS"]
    stored = events(session)
    assert stored["GS"].date_status == "confirmed"
    assert stored["MS"].date_status == "projected"  # расхождение дат
    assert stored["NFLX"].date_status == "projected"  # только один источник
    assert (stored["NFLX"].report_time, stored["GS"].fiscal_period) == ("AMC", "2026Q3")
    assert count(session, orm.EventJob) == 3 * JOBS_PER_EVENT
    synced = len(CONFIG.universe.tickers())
    assert count(session, orm.Company) == synced  # вселенная синхронизирована
    [change] = session.scalars(select(orm.EventChange)).all()
    assert (change.field, change.new_value) == ("date_check", "mismatch")
    assert change.reason == "DATA_CALENDAR: finnhub 2026-10-21 vs alphavantage 2026-10-22"
    assert notifier.messages == [
        (
            "MS: расхождение даты отчёта — finnhub 2026-10-21 vs alphavantage 2026-10-22",
            "DATA_CALENDAR",
        )
    ]


def test_repeat_run_does_not_duplicate_anything(session: Session) -> None:
    notifier = Notifier()
    for _ in range(2):
        result = agent(Source(FINNHUB), Source(ALPHAVANTAGE), notifier).run(
            session, as_of=AS_OF, now=NOW
        )
    assert (result.created, result.updated, result.mismatches) == ([], [], [])
    assert count(session, orm.Event) == 3
    assert count(session, orm.EventJob) == 3 * JOBS_PER_EVENT
    assert count(session, orm.EventChange) == 1
    assert len(notifier.messages) == 1  # о том же расхождении не сообщаем повторно


def test_moved_date_updates_event_logs_change_and_reschedules(session: Session) -> None:
    agent(Source(FINNHUB), Source(ALPHAVANTAGE), Notifier()).run(session, as_of=AS_OF, now=NOW)
    gs = events(session)["GS"]
    done = session.get(orm.EventJob, (gs.id, "T-14", "sector_cycle"))
    assert done is not None
    done.status = "done"
    before = session.get(orm.EventJob, (gs.id, "T0", "parse_report"))
    assert before is not None
    old_run_at = before.run_at
    old_done_at = done.run_at
    moved = [fh("GS", "2026-10-22"), *FINNHUB[1:]]
    result = agent(
        Source(moved), Source([av("GS", "2026-10-22"), *ALPHAVANTAGE[1:]]), Notifier()
    ).run(session, as_of=AS_OF, now=NOW)
    assert result.updated == ["GS"]
    assert count(session, orm.Event) == 3  # то же событие, не новое
    session.expire_all()
    gs = events(session)["GS"]
    assert (gs.report_date, gs.date_status) == (date(2026, 10, 22), "confirmed")
    changes = session.scalars(
        select(orm.EventChange).where(orm.EventChange.event_id == gs.id)
    ).all()
    assert [(c.field, c.old_value, c.new_value) for c in changes] == [
        ("report_date", "2026-10-20", "2026-10-22")
    ]
    after = session.get(orm.EventJob, (gs.id, "T0", "parse_report"))
    assert after is not None
    assert after.run_at != old_run_at
    kept = session.get(orm.EventJob, (gs.id, "T-14", "sector_cycle"))
    assert kept is not None
    assert (kept.status, kept.run_at) == ("done", old_done_at)  # выполненное не трогаем


def test_mismatch_resolved_then_new_mismatch_is_reported(session: Session) -> None:
    notifier = Notifier()
    agent(Source(FINNHUB), Source(ALPHAVANTAGE), notifier).run(session, as_of=AS_OF, now=NOW)
    fixed = [av("GS", "2026-10-20"), av("MS", "2026-10-21")]
    agent(Source(FINNHUB), Source(fixed), notifier).run(session, as_of=AS_OF, now=NOW)
    assert events(session)["MS"].date_status == "confirmed"
    again = [av("GS", "2026-10-20"), av("MS", "2026-10-23")]
    agent(Source(FINNHUB), Source(again), notifier).run(session, as_of=AS_OF, now=NOW)
    assert [code for _, code in notifier.messages] == ["DATA_CALENDAR", "DATA_CALENDAR"]


def test_alphavantage_down_creates_projected_events_and_notifies(session: Session) -> None:
    notifier = Notifier()
    result = agent(Source(FINNHUB), Source(DataError("alphavantage", "Note: limit")), notifier).run(
        session, as_of=AS_OF, now=NOW
    )
    assert len(result.created) == 3
    assert {e.date_status for e in events(session).values()} == {"projected"}
    assert notifier.messages[0][1] == "DATA_CALENDAR"
    assert "Alpha Vantage недоступен" in notifier.messages[0][0]


def test_finnhub_down_raises_and_notifies(session: Session) -> None:
    notifier = Notifier()
    with pytest.raises(DataError):
        agent(Source(DataError("finnhub", "HTTP 503")), Source(ALPHAVANTAGE), notifier).run(
            session, as_of=AS_OF, now=NOW
        )
    assert notifier.messages[0][1] == "DATA_CALENDAR"
    assert count(session, orm.Event) == 0


def test_event_without_fiscal_period_matches_by_nearest_date(session: Session) -> None:
    no_period = FinnhubEarning.model_validate({"symbol": "GS", "date": "2026-10-20", "hour": "bmo"})
    agent(Source([no_period]), Source([]), Notifier()).run(session, as_of=AS_OF, now=NOW)
    moved = FinnhubEarning.model_validate({"symbol": "GS", "date": "2026-10-23", "hour": "amc"})
    result = agent(Source([moved]), Source([]), Notifier()).run(session, as_of=AS_OF, now=NOW)
    assert result.updated == ["GS"]
    assert count(session, orm.Event) == 1
    gs = events(session)["GS"]
    assert (gs.report_date, gs.report_time, gs.fiscal_period) == (date(2026, 10, 23), "AMC", None)


def test_done_event_is_not_reused(session: Session) -> None:
    agent(Source([fh("GS", "2026-10-20")]), Source([]), Notifier()).run(
        session, as_of=AS_OF, now=NOW
    )
    events(session)["GS"].queue_status = "done"
    result = agent(Source([fh("GS", "2026-10-21", quarter=4)]), Source([]), Notifier()).run(
        session, as_of=AS_OF, now=NOW
    )
    assert result.created == ["GS"]
    assert count(session, orm.Event) == 2
