"""Ежедневный запуск агента «Календарь» из планировщика (SPEC §8: 06:00 ET, торговые дни)."""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from adapters.alphavantage.client import AlphaVantageClient, alphavantage_api_key
from adapters.cache import RedisCache
from adapters.finnhub.client import FinnhubClient, finnhub_api_key
from agents.calendar.agent import CalendarAgent, CalendarRunResult
from core.config import AppConfig, load_config
from core.error_log import logged_job
from core.scheduler.jobs import engine
from core.session_guard import is_trading_day, to_et
from notify.system import LoggingNotifier


def build_calendar_agent(config: AppConfig) -> CalendarAgent:
    """Боевые зависимости: Finnhub и Alpha Vantage с кэшем Redis, ключи из окружения."""
    cache = RedisCache.from_env(config.sources.redis.timeout_seconds)
    return CalendarAgent(
        finnhub=FinnhubClient.create(config.sources.finnhub, finnhub_api_key(), cache),
        alphavantage=AlphaVantageClient.create(
            config.sources.alphavantage, alphavantage_api_key(), cache
        ),
        notifier=LoggingNotifier(),
        universe=config.universe,
        schedule=config.schedule,
    )


@logged_job("calendar-daily", lambda: engine())
def run_calendar(
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    agent_factory: Callable[[AppConfig], CalendarAgent] = build_calendar_agent,
) -> CalendarRunResult | None:
    """Один прогон календаря; в неторговый день ничего не делает."""
    moment = now()
    as_of = to_et(moment).date()
    if not is_trading_day(as_of):
        return None
    agent = agent_factory(load_config())
    with Session(engine()) as session, session.begin():
        return agent.run(session, as_of=as_of, now=moment)
