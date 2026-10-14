from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.errors import DataError
from core.db import models as orm
from core.domain.schedule import EventJob
from core.error_log import MAX_MESSAGE_LENGTH, error_entry, logged_job, redact
from core.scheduler.dispatch import dispatch_due

NOW = datetime(2026, 10, 14, 19, 0, 30, tzinfo=UTC)


def test_redact_env_secrets_and_query_keys() -> None:
    env = {"MASSIVE_API_KEY": "secret-key-123", "HOME": "/Users/anton", "SHORT_TOKEN": "abc"}
    text = "GET https://x.io/a?apikey=AAA111&b=1 failed for secret-key-123 at /Users/anton (abc)"
    assert redact(text, env) == (
        "GET https://x.io/a?apikey=***&b=1 failed for *** at /Users/anton (abc)"
    )  # короткие значения и не-секреты не трогаются


def test_entry_keeps_type_and_truncates() -> None:
    entry = error_entry("options", ValueError("x" * 5000), at=NOW)
    assert (entry.error_type, len(entry.message)) == ("ValueError", MAX_MESSAGE_LENGTH)
    assert error_entry("calendar-daily", RuntimeError(), at=NOW).message == "RuntimeError"


def test_failed_event_job_is_logged_with_ticker_and_stage(session: Session) -> None:
    session.add(orm.Sector(id="tech", name="Tech", key_metrics=[]))
    session.flush()
    session.add(orm.Company(ticker="NFLX", sector_id="tech", name="Netflix"))
    event = orm.Event(ticker="NFLX", report_date=date(2026, 10, 20), date_status="confirmed")
    session.add(event)
    session.flush()
    session.add(
        orm.EventJob(event_id=event.id, stage="T-7", job="options", kind="analysis", run_at=NOW)
    )
    session.flush()

    def failing(session: Session, job: EventJob) -> None:
        raise DataError("massive", "HTTP 429 on https://api.massive.com/v2/aggs?apiKey=LEAK")

    result = dispatch_due(
        session, now=NOW, grace=timedelta(minutes=5), handlers={"options": failing}
    )
    assert len(result.failed) == 1
    row = session.scalars(select(orm.ErrorLog)).one()
    assert (row.source, row.ticker, row.stage, row.error_type) == (
        "options",
        "NFLX",
        "T-7",
        "DataError",
    )
    assert "HTTP 429" in row.message
    assert "LEAK" not in row.message


def test_daily_job_error_is_logged_and_reraised(session: Session) -> None:
    @logged_job("calendar-daily", lambda: session.connection().engine)
    def broken() -> None:
        raise RuntimeError("finnhub down")

    # отдельная сессия журнала пишет в ту же тестовую базу — проверяем через неё же
    with pytest.raises(RuntimeError, match="finnhub down"):
        broken()
    with Session(session.connection().engine) as other:
        rows = other.scalars(
            select(orm.ErrorLog).where(orm.ErrorLog.source == "calendar-daily")
        ).all()
        assert [r.message for r in rows][-1:] == ["finnhub down"]
        for r in rows:  # тестовая база общая: убираем за собой
            other.delete(r)
        other.commit()


def test_first_success_after_error_logs_recovery_once(session: Session) -> None:
    session.add(orm.Sector(id="tech", name="Tech", key_metrics=[]))
    session.flush()
    session.add_all(
        [
            orm.Company(ticker="NFLX", sector_id="tech", name="Netflix"),
            orm.Company(ticker="TSLA", sector_id="tech", name="Tesla"),
        ]
    )
    ids = {}
    for ticker in ("NFLX", "TSLA"):
        event = orm.Event(ticker=ticker, report_date=date(2026, 10, 20), date_status="confirmed")
        session.add(event)
        session.flush()
        ids[ticker] = event.id
    session.add(error_entry("options", RuntimeError("HTTP 429"), at=NOW, event_id=ids["NFLX"]))
    later = NOW + timedelta(days=1)
    for ticker in ("TSLA", "NFLX"):  # два успеха подряд — запись «работает» одна
        session.add(
            orm.EventJob(
                event_id=ids[ticker], stage="T-3", job="options", kind="analysis", run_at=later
            )
        )
    session.flush()
    result = dispatch_due(
        session, now=later, grace=timedelta(minutes=5), handlers={"options": lambda s, j: None}
    )
    assert len(result.done) == 2
    rows = session.scalars(select(orm.ErrorLog).order_by(orm.ErrorLog.id)).all()
    assert [(r.level, r.ticker) for r in rows] == [("error", None), ("ok", "TSLA")]
    assert rows[1].message == "Задача снова работает (TSLA T-3)."


def test_daily_job_success_after_error_logs_recovery(session: Session) -> None:
    engine = session.connection().engine
    calls = iter([RuntimeError("finnhub down"), None, None])

    @logged_job("consensus-daily-test", lambda: engine)
    def flaky() -> None:
        error = next(calls)
        if error is not None:
            raise error

    with pytest.raises(RuntimeError):
        flaky()
    flaky()
    flaky()
    with Session(engine) as other:
        rows = other.scalars(
            select(orm.ErrorLog)
            .where(orm.ErrorLog.source == "consensus-daily-test")
            .order_by(orm.ErrorLog.id)
        ).all()
        assert [r.level for r in rows] == ["error", "ok"]
        for r in rows:  # тестовая база общая: убираем за собой
            other.delete(r)
        other.commit()
