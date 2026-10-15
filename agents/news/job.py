"""Ежедневный сбор новостей компаний и тегов (E6): 07:45 ET, до утреннего дайджеста."""

import os
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from adapters.cache import RedisCache
from adapters.llm.client import LlmClient, anthropic_api_key
from adapters.massive.client import MassiveClient, massive_api_key
from agents.news.collect import Extractor, NewsRunResult, NewsSource, collect_news
from core.config import AppConfig, load_config
from core.error_log import logged_job
from core.scheduler.jobs import engine
from core.session_guard import is_trading_day, to_et


def build_sources(config: AppConfig) -> tuple[NewsSource, Extractor | None]:  # pragma: no cover
    """Massive с кэшем Redis; LLM — если задан ANTHROPIC_API_KEY (без него новости без тегов)."""
    cache = RedisCache.from_env(config.sources.redis.timeout_seconds)
    news = MassiveClient.create(config.sources.massive, massive_api_key(), cache)
    llm = (
        LlmClient.create_default(config.sources.llm, anthropic_api_key())
        if os.environ.get("ANTHROPIC_API_KEY", "").strip()
        else None
    )
    return news, llm


@logged_job("news-daily", lambda: engine())
def run_news(
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sources_factory: Callable[[AppConfig], tuple[NewsSource, Extractor | None]] = build_sources,
) -> NewsRunResult | None:
    """Задача планировщика; в неторговый день ничего не делает."""
    today = to_et(now()).date()
    if not is_trading_day(today):
        return None
    config = load_config()
    news, llm = sources_factory(config)
    with Session(engine()) as session:
        return collect_news(session, news, llm, config.universe.tickers(), today)
