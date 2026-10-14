"""Фабрика плагина «Консенсус» для реестра (T13)."""

from adapters.alphavantage.client import AlphaVantageClient, alphavantage_api_key
from adapters.cache import RedisCache
from agents.consensus.agent import ConsensusAgentPlugin
from core.config import AppConfig


def create_plugin(config: AppConfig) -> ConsensusAgentPlugin:  # pragma: no cover
    sources = config.sources
    cache = RedisCache.from_env(sources.redis.timeout_seconds)
    return ConsensusAgentPlugin(
        AlphaVantageClient.create(sources.alphavantage, alphavantage_api_key(), cache),
        config.thresholds.agents.consensus,
    )
