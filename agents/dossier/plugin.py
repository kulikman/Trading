"""Фабрика плагина «Досье» для реестра (T13)."""

from adapters.cache import RedisCache
from adapters.edgar.client import EdgarClient, sec_user_agent
from adapters.finnhub.client import FinnhubClient, finnhub_api_key
from adapters.llm.client import LlmClient, anthropic_api_key
from adapters.massive.client import MassiveClient, massive_api_key
from agents.dossier.agent import DossierAgentPlugin
from core.config import AppConfig


def create_plugin(config: AppConfig) -> DossierAgentPlugin:  # pragma: no cover
    sources = config.sources
    cache = RedisCache.from_env(sources.redis.timeout_seconds)
    return DossierAgentPlugin(
        EdgarClient.create(sources.edgar, sec_user_agent(), cache),
        MassiveClient.create(sources.massive, massive_api_key(), cache),
        FinnhubClient.create(sources.finnhub, finnhub_api_key(), cache),
        LlmClient.create_default(sources.llm, anthropic_api_key()),
        config.thresholds.agents.dossier,
        sources.edgar.archives_base_url,
        config.universe.sec_predecessor_ciks(),
    )
