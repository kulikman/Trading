"""Точки входа, которые APScheduler вызывает по имени (хранилище в Postgres хранит ссылку)."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import cache

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from core.config import load_config
from core.db.session import create_db_engine
from core.registry.agent_jobs import agent_handlers
from core.registry.loader import load_agents, load_strategies
from core.scheduler.dispatch import HANDLERS, DispatchResult, Handler, dispatch_due
from decision.jobs import decision_handlers
from models.forecast import forecast_handlers


@cache
def engine() -> Engine:
    return create_db_engine()


@cache
def handlers() -> dict[str, Handler]:
    """Обработчики задач: встроенные, агенты, прогноз и решения (один раз на процесс)."""
    config = load_config()
    return {
        **HANDLERS,
        **agent_handlers(config.schedule, load_agents(config)),
        **forecast_handlers(config.registry, config.thresholds.models),
        **decision_handlers(config, load_strategies(config)),
    }


def run_dispatch(
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    job_handlers: Callable[[], dict[str, Handler]] = handlers,
) -> DispatchResult:
    """Наступившие задачи событий — в одной транзакции."""
    grace = timedelta(seconds=load_config().schedule.scheduler.misfire_grace_seconds)
    with Session(engine()) as session, session.begin():
        return dispatch_due(session, now=now(), grace=grace, handlers=job_handlers())
