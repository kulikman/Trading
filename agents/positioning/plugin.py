"""Фабрика плагина «Позиционирование» для реестра (T13)."""

from adapters.cache import RedisCache
from adapters.massive.client import MassiveClient, massive_api_key
from agents.positioning.agent import PositioningAgentPlugin
from core.config import AppConfig


def create_plugin(config: AppConfig) -> PositioningAgentPlugin:  # pragma: no cover
    sources = config.sources
    cache = RedisCache.from_env(sources.redis.timeout_seconds)
    return PositioningAgentPlugin(
        MassiveClient.create(sources.massive, massive_api_key(), cache),
        config.thresholds.agents.positioning,
    )
