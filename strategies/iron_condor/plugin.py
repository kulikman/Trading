"""Фабрика плагина «Iron condor» для реестра (T13)."""

from adapters.cache import RedisCache
from adapters.massive.client import MassiveClient, massive_api_key
from core.config import AppConfig
from strategies.base import dependencies
from strategies.iron_condor.strategy import IronCondorStrategy


def create_plugin(config: AppConfig) -> IronCondorStrategy:  # pragma: no cover
    costs, rate = dependencies(config)
    cache = RedisCache.from_env(config.sources.redis.timeout_seconds)
    stocks = MassiveClient.create(config.sources.massive, massive_api_key(), cache)
    chain = MassiveClient.create_history(config.sources.massive, massive_api_key(), cache)
    return IronCondorStrategy(stocks, costs, config.thresholds, rate, chain)
