"""Фабрика плагина «Режим A» для реестра (T13)."""

from adapters.cache import RedisCache
from adapters.massive.client import MassiveClient, massive_api_key
from core.config import AppConfig
from strategies.base import dependencies
from strategies.mode_a.strategy import ModeAStrategy


def create_plugin(config: AppConfig) -> ModeAStrategy:  # pragma: no cover
    costs, rate = dependencies(config)
    cache = RedisCache.from_env(config.sources.redis.timeout_seconds)
    stocks = MassiveClient.create(config.sources.massive, massive_api_key(), cache)
    return ModeAStrategy(stocks, costs, config.thresholds, rate)
