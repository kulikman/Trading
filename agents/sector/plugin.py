"""Фабрика плагина «Сектор» для реестра (T13)."""

from adapters.cache import RedisCache
from adapters.massive.client import MassiveClient, massive_api_key
from agents.sector.agent import SectorAgentPlugin
from core.config import AppConfig


def create_plugin(config: AppConfig) -> SectorAgentPlugin:  # pragma: no cover
    sources = config.sources
    cache = RedisCache.from_env(sources.redis.timeout_seconds)
    return SectorAgentPlugin(
        MassiveClient.create(sources.massive, massive_api_key(), cache),
        config.universe,
        config.thresholds.agents.sector,
    )
