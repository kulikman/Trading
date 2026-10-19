"""Воскресный агент: проверяет у каких тикеров из watchlist.yaml есть отчёт на текущей неделе.

Запускается каждое воскресенье в 18:00 ET. Пишет список активных тикеров в Redis
(ключ `universe:watchlist_active`, TTL 8 дней). load_config() читает этот ключ
и временно расширяет Universe до следующего воскресенья.
"""

import json
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from adapters.cache import RedisCache
from adapters.finnhub.client import FinnhubClient, finnhub_api_key
from core.config import DEFAULT_CONFIG_DIR, load_universe
from core.error_log import logged_job
from core.scheduler.jobs import engine
from core.session_guard import to_et

logger = logging.getLogger(__name__)

REDIS_KEY = "universe:watchlist_active"
REDIS_TTL_SECONDS = 8 * 24 * 3600  # 8 дней — с запасом до следующего воскресенья


def _redis_client() -> redis.Redis:
    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        raise RuntimeError("REDIS_URL is not set")
    return redis.Redis.from_url(
        url,
        socket_connect_timeout=5.0,
        socket_timeout=5.0,
        retry=Retry(NoBackoff(), 0),
    )


@logged_job("watchlist-refresh", lambda: engine())
def run_watchlist_refresh(
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> list[str]:
    """Определяет активные тикеры watchlist на предстоящую неделю, пишет в Redis."""
    from core.config import load_sources

    moment = now()
    today = to_et(moment).date()

    # Окно: следующие 7 календарных дней (пн–пт попадут внутрь)
    week_start = today + timedelta(days=1)
    week_end = today + timedelta(days=7)

    sources = load_sources(DEFAULT_CONFIG_DIR / "sources.yaml")
    cache = RedisCache.from_env(sources.redis.timeout_seconds)
    finnhub = FinnhubClient.create(sources.finnhub, finnhub_api_key(), cache)

    watchlist_path = DEFAULT_CONFIG_DIR / "watchlist.yaml"
    if not watchlist_path.exists():
        logger.warning("watchlist.yaml not found, skipping refresh")
        return []

    watchlist = load_universe(watchlist_path)
    watchlist_tickers = set(watchlist.tickers())

    # Запрашиваем календарь на неделю вперёд без фильтра по символу — один запрос
    try:
        rows = finnhub.earnings_calendar(week_start, week_end, symbol=None)
    except Exception as exc:
        logger.error("watchlist-refresh: Finnhub error: %s", exc)
        return []

    active = sorted({r.symbol for r in rows if r.symbol in watchlist_tickers})

    try:
        client = _redis_client()
        client.set(REDIS_KEY, json.dumps(active), ex=REDIS_TTL_SECONDS)
    except Exception as exc:
        logger.error("watchlist-refresh: Redis write failed: %s", exc)
        return active

    logger.info(
        "watchlist-refresh: %d active tickers for %s–%s: %s",
        len(active),
        week_start,
        week_end,
        active,
    )
    return active
