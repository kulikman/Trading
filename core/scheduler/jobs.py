"""Точки входа, которые APScheduler вызывает по имени (хранилище в Postgres хранит ссылку)."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import cache

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from adapters.finnhub.client import FinnhubClient, finnhub_api_key
from adapters.health import drain
from core.config import load_config
from core.db.session import create_db_engine
from core.error_log import logged_job
from core.registry.agent_jobs import agent_handlers
from core.registry.loader import load_agents, load_strategies
from core.scheduler.dispatch import HANDLERS, DispatchResult, Handler, dispatch_due
from decision.jobs import decision_handlers
from decision.report import report_handlers
from models.forecast import forecast_handlers
from notify.signals import send_new_signals
from notify.system import collect_error_messages, save_source_health, send_system_messages
from notify.telegram.client import TelegramClient

logger = logging.getLogger(__name__)


@cache
def engine() -> Engine:
    return create_db_engine()


@cache
def handlers() -> dict[str, Handler]:
    """Обработчики задач: встроенные, агенты, прогноз, решения, разбор отчёта (раз на процесс)."""
    config = load_config()
    return {
        **HANDLERS,
        **agent_handlers(config.schedule, load_agents(config)),
        **forecast_handlers(config.registry, config.thresholds.models),
        **decision_handlers(config, load_strategies(config)),
        # без кэша: в день T0 нужен свежий факт отчёта
        **report_handlers(FinnhubClient.create(config.sources.finnhub, finnhub_api_key())),
    }


def run_dispatch(
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    job_handlers: Callable[[], dict[str, Handler]] = handlers,
) -> DispatchResult:
    """Наступившие задачи событий — в одной транзакции."""
    grace = timedelta(seconds=load_config().schedule.scheduler.misfire_grace_seconds)
    with Session(engine()) as session, session.begin():
        result = dispatch_due(session, now=now(), grace=grace, handlers=job_handlers())
    for notify in (run_signal_notifications, run_system_messages):
        try:
            notify()
        except Exception:  # уже в журнале ошибок (logged_job); диспетчер не падает из-за Telegram
            logger.exception("telegram notification failed", extra={"job": notify.__name__})
    return result


@logged_job("system-messages", lambda: engine())
def run_system_messages(now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> int:
    """Состояние источников → source_status; сбои задач → «СИСТЕМА»; отправка в Telegram."""
    with Session(engine()) as session:
        save_source_health(session, drain())
        collect_error_messages(session)
        session.commit()
        client = TelegramClient.from_env()
        return 0 if client is None else send_system_messages(session, client, now())


@logged_job("telegram-signals", lambda: engine())
def run_signal_notifications() -> int:
    """Сообщения о новых paper-входах (SPEC §12); бот не настроен — ничего не делает."""
    client = TelegramClient.from_env()
    if client is None:
        return 0
    with Session(engine()) as session:
        return send_new_signals(session, client, load_config().thresholds)
