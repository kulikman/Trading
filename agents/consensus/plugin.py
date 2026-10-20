"""Фабрика плагина «Консенсус» для реестра (T13)."""

import os

from adapters.alphavantage.client import AlphaVantageClient, alphavantage_api_key
from adapters.cache import RedisCache
from adapters.fmp.client import FmpClient
from agents.consensus.agent import ConsensusAgentPlugin, EstimatesSource, FallbackEstimatesSource
from core.config import AppConfig


def create_plugin(config: AppConfig) -> ConsensusAgentPlugin:  # pragma: no cover
    sources = config.sources
    cache = RedisCache.from_env(sources.redis.timeout_seconds)
    av = AlphaVantageClient.create(sources.alphavantage, alphavantage_api_key(), cache)

    fmp_key = os.environ.get("FMP_API_KEY", "").strip()
    estimates: EstimatesSource
    if fmp_key:
        fmp = FmpClient.create(sources.fmp, fmp_key, cache)
        estimates = FallbackEstimatesSource(av, fmp)
    else:
        estimates = av

    return ConsensusAgentPlugin(estimates, config.thresholds.agents.consensus)
