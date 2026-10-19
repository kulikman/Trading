"""Фабрика плагина «Консенсус» для реестра (T13)."""

from adapters.alphavantage.client import AlphaVantageClient, alphavantage_api_key
from adapters.cache import RedisCache
from adapters.fmp.client import FmpClient, fmp_api_key
from agents.consensus.agent import ConsensusAgentPlugin, FallbackEstimatesSource
from core.config import AppConfig


def create_plugin(config: AppConfig) -> ConsensusAgentPlugin:  # pragma: no cover
    sources = config.sources
    cache = RedisCache.from_env(sources.redis.timeout_seconds)
    av = AlphaVantageClient.create(sources.alphavantage, alphavantage_api_key(), cache)
    fmp = FmpClient.create(sources.fmp, fmp_api_key(), cache)
    return ConsensusAgentPlugin(
        FallbackEstimatesSource(av, fmp),
        config.thresholds.agents.consensus,
    )
