"""Точки входа, которые APScheduler вызывает по имени (хранилище в Postgres хранит ссылку)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import cache

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from core.config import load_config
from core.db.session import create_db_engine
from core.scheduler.dispatch import HANDLERS, DispatchResult, dispatch_due


@cache
def engine() -> Engine:
    return create_db_engine()


def run_dispatch(now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> DispatchResult:
    """Наступившие задачи событий — в одной транзакции."""
    grace = timedelta(seconds=load_config().schedule.scheduler.misfire_grace_seconds)
    with Session(engine()) as session, session.begin():
        return dispatch_due(session, now=now(), grace=grace, handlers=HANDLERS)
