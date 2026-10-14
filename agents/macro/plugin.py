"""Фабрика плагина «Макро» для реестра (T13)."""

from adapters.cache import RedisCache
from adapters.fred.client import FredClient, fred_api_key
from adapters.massive.client import MassiveClient, massive_api_key
from agents.macro.agent import MacroAgentPlugin
from core.config import AppConfig


def create_plugin(config: AppConfig) -> MacroAgentPlugin:  # pragma: no cover
    sources = config.sources
    cache = RedisCache.from_env(sources.redis.timeout_seconds)
    return MacroAgentPlugin(
        FredClient.create(sources.fred, fred_api_key(), cache),
        MassiveClient.create(sources.massive, massive_api_key(), cache),
        config.thresholds.risk_limits.black_swan,
        config.thresholds.agents.macro,
    )
