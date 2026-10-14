"""Ежедневный снимок консенсуса из планировщика (SPEC §8: «ежедневно в сезон»; TASKS T06).

Бесплатные источники отдают только текущую оценку — история пересмотров копится здесь.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from adapters.cache import RedisCache
from adapters.finnhub.client import FinnhubClient, finnhub_api_key
from agents.consensus.snapshot import EarningsCalendarSource, take_consensus_snapshot
from core.config import AppConfig, load_config
from core.error_log import logged_job
from core.scheduler.jobs import engine
from core.session_guard import is_trading_day, to_et

logger = logging.getLogger(__name__)


def build_source(config: AppConfig) -> EarningsCalendarSource:
    """Календарь Finnhub с кэшем Redis (бесплатно, 60 запросов в минуту)."""
    cache = RedisCache.from_env(config.sources.redis.timeout_seconds)
    return FinnhubClient.create(config.sources.finnhub, finnhub_api_key(), cache)


@logged_job("consensus-daily", lambda: engine())
def run_consensus_snapshot(
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    source_factory: Callable[[AppConfig], EarningsCalendarSource] = build_source,
) -> int | None:
    """Снимок на сегодня; в неторговый день ничего не делает. Возвращает число строк."""
    as_of = to_et(now()).date()
    if not is_trading_day(as_of):
        return None
    config = load_config()
    source = source_factory(config)
    with Session(engine()) as session, session.begin():
        rows = take_consensus_snapshot(
            source,
            session,
            as_of=as_of,
            lookahead_days=config.sources.finnhub.consensus_lookahead_days,
            tickers=config.universe.tickers(),
        )
    logger.info("consensus snapshot", extra={"rows": rows, "as_of": str(as_of)})
    return rows
