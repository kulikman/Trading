"""Фабрика плагина «Опционы» для реестра (T13)."""

from adapters.cache import RedisCache
from adapters.fred.client import FredClient, fred_api_key
from adapters.massive.client import MassiveClient, massive_api_key
from agents.options.agent import OptionsAgentPlugin
from core.config import AppConfig


def create_plugin(config: AppConfig) -> OptionsAgentPlugin:  # pragma: no cover
    sources = config.sources
    cache = RedisCache.from_env(sources.redis.timeout_seconds)
    return OptionsAgentPlugin(
        # клиент истории: ~5 запросов в минуту к опционам, паузы при 429
        MassiveClient.create_history(sources.massive, massive_api_key(), cache),
        FredClient.create(sources.fred, fred_api_key(), cache),
        sources.massive.history,
        config.thresholds.agents.options,
    )
