import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import Engine, delete, func, select, text
from sqlalchemy.orm import Session

from adapters.finnhub.client import FinnhubClient
from agents.calendar import job as calendar_job
from agents.calendar.agent import CalendarAgent, CalendarRunResult
from agents.consensus import job as consensus_job
from core.config import load_config
from core.db import models as orm
from core.domain.schedule import EventJob
from core.scheduler import __main__ as scheduler_main
from core.scheduler import jobs as scheduler_jobs
from core.scheduler.dispatch import dispatch_due
from core.scheduler.runner import (
    ARCHIVE_JOB_ID,
    CALENDAR_JOB_ID,
    CONSENSUS_JOB_ID,
    DISPATCH_JOB_ID,
    EVENING_DIGEST_JOB_ID,
    JOBS_TABLE,
    MORNING_DIGEST_JOB_ID,
    TRAILING_JOB_ID,
    create_scheduler,
    register_jobs,
)

NOW = datetime(2026, 10, 13, 19, 30, tzinfo=UTC)
GRACE = timedelta(minutes=5)
SCHEDULE = load_config().schedule


def seed_event(session: Session) -> int:
    session.add(orm.Sector(id="banks", name="Банки", key_metrics=["NII"]))
    session.flush()  # без relationship порядок INSERT не гарантирован
    session.add(orm.Company(ticker="GS", sector_id="banks", name="GS"))
    event = orm.Event(ticker="GS", report_date=date(2026, 10, 14), date_status="projected")
    session.add(event)
    session.flush()
    return event.id


def add_job(
    session: Session, event_id: int, job: str, run_at: datetime, status: str = "planned"
) -> None:
    session.add(
        orm.EventJob(
            event_id=event_id, stage="T-1", job=job, kind="analysis", run_at=run_at, status=status
        )
    )
    session.flush()


def statuses(session: Session) -> dict[str, str]:
    return {r.job: r.status for r in session.scalars(select(orm.EventJob)).all()}


def test_dispatch_runs_due_jobs_once(session: Session) -> None:
    event_id = seed_event(session)
    add_job(session, event_id, "options", NOW - timedelta(minutes=1))
    add_job(session, event_id, "forecast", NOW - timedelta(minutes=1))
    add_job(session, event_id, "unknown_job", NOW)
    add_job(session, event_id, "stale", NOW - timedelta(hours=2))
    add_job(session, event_id, "future", NOW + timedelta(minutes=1))
    add_job(session, event_id, "already", NOW - timedelta(minutes=1), status="done")
    calls: list[EventJob] = []

    def ok(_: Session, job: EventJob) -> None:
        calls.append(job)

    def boom(_: Session, job: EventJob) -> None:
        raise RuntimeError("handler bug")

    handlers = {"options": ok, "forecast": boom}
    result = dispatch_due(session, now=NOW, grace=GRACE, handlers=handlers)
    assert [j.job for j in calls] == ["options"]
    assert statuses(session) == {
        "options": "done",
        "forecast": "failed",
        "unknown_job": "no_handler",
        "stale": "missed",
        "future": "planned",
        "already": "done",
    }
    assert (len(result.done), len(result.failed), len(result.no_handler), len(result.missed)) == (
        1,
        1,
        1,
        1,
    )
    again = dispatch_due(session, now=NOW, grace=GRACE, handlers=handlers)
    assert (again.done, again.failed, again.missed, again.no_handler) == ([], [], [], [])
    assert len(calls) == 1


def test_register_jobs_in_postgres_store_is_idempotent(
    test_database_url: str, engine: Engine
) -> None:
    scheduler = BackgroundScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=test_database_url, tablename=JOBS_TABLE)},
        timezone="UTC",
    )
    scheduler.start(paused=True)
    try:
        register_jobs(scheduler, SCHEDULE)
        register_jobs(scheduler, SCHEDULE)
        jobs = {j.id: j for j in scheduler.get_jobs()}
        assert set(jobs) == {
            CALENDAR_JOB_ID,
            ARCHIVE_JOB_ID,
            CONSENSUS_JOB_ID,
            TRAILING_JOB_ID,
            MORNING_DIGEST_JOB_ID,
            EVENING_DIGEST_JOB_ID,
            DISPATCH_JOB_ID,
        }
        trailing = jobs[TRAILING_JOB_ID].trigger
        assert isinstance(trailing, CronTrigger)
        trailing_fields = {f.name: str(f) for f in trailing.fields}
        assert (trailing_fields["hour"], trailing_fields["minute"]) == ("16", "20")
        consensus = jobs[CONSENSUS_JOB_ID].trigger
        assert isinstance(consensus, CronTrigger)
        consensus_fields = {f.name: str(f) for f in consensus.fields}
        assert (consensus_fields["hour"], consensus_fields["minute"]) == ("6", "10")
        archive = jobs[ARCHIVE_JOB_ID].trigger
        assert isinstance(archive, CronTrigger)
        archive_fields = {f.name: str(f) for f in archive.fields}
        assert (archive_fields["hour"], archive_fields["minute"]) == ("18", "30")
        calendar = jobs[CALENDAR_JOB_ID].trigger
        assert isinstance(calendar, CronTrigger)
        fields = {f.name: str(f) for f in calendar.fields}
        assert (fields["day_of_week"], fields["hour"], fields["minute"]) == ("mon-fri", "6", "0")
        assert str(calendar.timezone) == "America/New_York"
        dispatch = jobs[DISPATCH_JOB_ID].trigger
        assert isinstance(dispatch, IntervalTrigger)
        assert dispatch.interval == timedelta(seconds=SCHEDULE.scheduler.dispatch_interval_seconds)
        with engine.connect() as connection:
            stored = connection.execute(
                select(func.count()).select_from(orm.apscheduler_jobs)
            ).scalar_one()
        assert stored == 7
    finally:
        scheduler.shutdown(wait=False)
        with engine.begin() as connection:
            connection.execute(delete(orm.apscheduler_jobs))


def test_create_scheduler_uses_postgres_store(test_database_url: str) -> None:
    scheduler = create_scheduler(test_database_url)
    store = scheduler._jobstores["default"]
    assert isinstance(store, SQLAlchemyJobStore)
    assert store.jobs_t.name == JOBS_TABLE


def test_main_registers_and_starts(monkeypatch: pytest.MonkeyPatch, test_database_url: str) -> None:
    started: list[bool] = []

    class FakeScheduler:
        def __init__(self) -> None:
            self.ids: list[str] = []

        def add_job(self, *args: Any, **kwargs: Any) -> None:
            self.ids.append(kwargs["id"])

        def start(self) -> None:
            started.append(True)

    fake = FakeScheduler()
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setattr(scheduler_main, "create_scheduler", lambda url: fake)
    monkeypatch.setattr(scheduler_main, "handlers", dict)  # агенты требуют ключей API
    synced: list[int] = []
    monkeypatch.setattr(
        scheduler_main,
        "sync_plugins",
        lambda session, registry: synced.append(len(registry.plugins)),
    )
    scheduler_main.main()
    assert synced == [len(load_config().registry.plugins)]  # реестр синхронизирован при старте
    # адреса запросов (с ключами FRED / Alpha Vantage) не пишутся в лог планировщика
    assert logging.getLogger("httpx").level == logging.WARNING
    assert (fake.ids, started) == (
        [
            CALENDAR_JOB_ID,
            ARCHIVE_JOB_ID,
            CONSENSUS_JOB_ID,
            TRAILING_JOB_ID,
            MORNING_DIGEST_JOB_ID,
            EVENING_DIGEST_JOB_ID,
            DISPATCH_JOB_ID,
        ],
        [True],
    )


@pytest.fixture
def isolated_engine(monkeypatch: pytest.MonkeyPatch, engine: Engine) -> Engine:
    monkeypatch.setattr(scheduler_jobs, "engine", lambda: engine)
    monkeypatch.setattr(calendar_job, "engine", lambda: engine)
    return engine


def test_run_dispatch_entry_point(isolated_engine: Engine) -> None:
    with isolated_engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM event_job")).scalar_one() == 0
    result = scheduler_jobs.run_dispatch(now=lambda: NOW, job_handlers=dict)
    assert (result.done, result.missed) == ([], [])


class FakeAgent:
    def __init__(self) -> None:
        self.calls: list[tuple[date, datetime]] = []

    def run(self, session: Session, *, as_of: date, now: datetime) -> CalendarRunResult:
        self.calls.append((as_of, now))
        return CalendarRunResult()


def test_run_calendar_skips_non_trading_days_and_runs_on_trading_days(
    isolated_engine: Engine,
) -> None:
    fake = FakeAgent()

    def factory(config: Any) -> Any:
        return fake

    saturday = datetime(2026, 10, 17, 10, 0, tzinfo=UTC)
    assert calendar_job.run_calendar(now=lambda: saturday, agent_factory=factory) is None
    tuesday = datetime(2026, 10, 13, 10, 0, tzinfo=UTC)
    assert isinstance(
        calendar_job.run_calendar(now=lambda: tuesday, agent_factory=factory), CalendarRunResult
    )
    assert fake.calls == [(date(2026, 10, 13), tuesday)]


def test_build_calendar_agent_wires_real_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "fh-fake")
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "av-fake")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    assert isinstance(calendar_job.build_calendar_agent(load_config()), CalendarAgent)


class CalendarSource:
    def __init__(self) -> None:
        self.calls: list[tuple[date, date]] = []

    def earnings_calendar(self, start: date, end: date, symbol: str | None = None) -> list[Any]:
        self.calls.append((start, end))
        return []  # строки не пишутся: тест не оставляет данных в общей тестовой базе


def test_run_consensus_snapshot_on_trading_days_only(
    monkeypatch: pytest.MonkeyPatch, engine: Engine
) -> None:
    monkeypatch.setattr(consensus_job, "engine", lambda: engine)
    source = CalendarSource()

    def factory(config: Any) -> CalendarSource:
        return source

    saturday = datetime(2026, 10, 17, 10, 10, tzinfo=UTC)
    assert (
        consensus_job.run_consensus_snapshot(now=lambda: saturday, source_factory=factory) is None
    )
    tuesday = datetime(2026, 10, 13, 10, 10, tzinfo=UTC)
    assert consensus_job.run_consensus_snapshot(now=lambda: tuesday, source_factory=factory) == 0
    lookahead = load_config().sources.finnhub.consensus_lookahead_days
    assert source.calls == [(date(2026, 10, 13), date(2026, 10, 13) + timedelta(days=lookahead))]


def test_build_consensus_source_wires_finnhub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "fh-fake")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    assert isinstance(consensus_job.build_source(load_config()), FinnhubClient)
