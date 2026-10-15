"""Фабрика плагина «Режим C» для реестра (T16)."""

from adapters.cache import RedisCache
from adapters.finnhub.client import FinnhubClient, finnhub_api_key
from adapters.massive.client import MassiveClient, massive_api_key
from core.config import AppConfig
from strategies.base import dependencies
from strategies.mode_c.strategy import ModeCStrategy


def create_plugin(config: AppConfig) -> ModeCStrategy:  # pragma: no cover
    costs, rate = dependencies(config)
    cache = RedisCache.from_env(config.sources.redis.timeout_seconds)
    stocks = MassiveClient.create(config.sources.massive, massive_api_key(), cache)
    reports = FinnhubClient.create(config.sources.finnhub, finnhub_api_key())
    return ModeCStrategy(stocks, reports, costs, config.thresholds, rate)
