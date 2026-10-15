"""Модель config/sources.yaml: технические параметры адаптеров."""

from typing import Literal

from pydantic import Field

from core.config.base import PositiveFloat, PositiveInt, StrictModel


class MassivePageLimit(StrictModel):
    aggregates: int = Field(gt=0, le=50000)
    option_contracts: int = Field(gt=0, le=1000)
    option_chain: int = Field(gt=0, le=250)
    news: int = Field(gt=0, le=1000)


class MassiveCacheTtl(StrictModel):
    aggregates: int = Field(ge=0)
    intraday_aggregates: int = Field(ge=0)  # минутные и часовые свечи: день ещё идёт
    last_quote: int = Field(ge=0)
    snapshot: int = Field(ge=0)
    option_contracts: int = Field(ge=0)
    option_chain: int = Field(ge=0)
    news: int = Field(ge=0)
    ticker_events: int = Field(ge=0)
    short_interest: int = Field(ge=0)


class MassiveImpliedMove(StrictModel):
    expiration_lookahead_days: PositiveInt
    max_plausible_iv: PositiveFloat


class MassiveHistory(StrictModel):
    """Исторические опционы (T10): лимит запросов, окно цен вокруг отчёта, выбор страйков."""

    archive_days: PositiveInt
    stock_history_days: PositiveInt
    requests_per_minute: PositiveInt
    max_attempts: PositiveInt
    backoff_base_seconds: float = Field(ge=0)
    days_before: PositiveInt
    days_after: int = Field(ge=0)
    expiration_lookahead_days: PositiveInt
    strike_band: float = Field(gt=0, lt=1)
    max_strike_attempts: PositiveInt
    risk_free_rate: float = Field(ge=0, lt=0.2)


class MassiveSettings(StrictModel):
    base_url: str = Field(pattern=r"^https://")
    timeout_seconds: PositiveFloat
    max_attempts: PositiveInt
    backoff_base_seconds: float = Field(ge=0)
    max_pages: PositiveInt
    page_limit: MassivePageLimit
    cache_ttl_seconds: MassiveCacheTtl
    implied_move: MassiveImpliedMove
    history: MassiveHistory


class HttpSourceSettings(StrictModel):
    base_url: str = Field(pattern=r"^https://")
    timeout_seconds: PositiveFloat
    max_attempts: PositiveInt
    backoff_base_seconds: float = Field(ge=0)


class FinnhubCacheTtl(StrictModel):
    earnings_calendar: int = Field(ge=0)
    earnings_history: int = Field(ge=0)


class FinnhubSettings(HttpSourceSettings):
    consensus_lookahead_days: PositiveInt
    calendar_chunk_days: PositiveInt
    calendar_row_cap: int = Field(ge=2)
    cache_ttl_seconds: FinnhubCacheTtl


class AlphaVantageCacheTtl(StrictModel):
    earnings_calendar: int = Field(ge=0)
    earnings_estimates: int = Field(ge=0)
    earnings: int = Field(ge=0)


class AlphaVantageSettings(HttpSourceSettings):
    calendar_horizon: Literal["3month", "6month", "12month"]
    cache_ttl_seconds: AlphaVantageCacheTtl


class EdgarCacheTtl(StrictModel):
    tickers: int = Field(ge=0)
    submissions: int = Field(ge=0)
    submissions_history: int = Field(ge=0)
    company_facts: int = Field(ge=0)
    documents: int = Field(ge=0)


class EdgarFinancials(StrictModel):
    quarters: PositiveInt
    quarter_days_min: PositiveInt
    quarter_days_max: PositiveInt
    non_additive_metrics: list[str]
    concepts: dict[str, list[str]] = Field(min_length=1)


class EdgarArchive(StrictModel):
    """Сборка архива отчётов (T11): выручка из XBRL и сверка дат с 8-K."""

    revenue_quarters: PositiveInt
    fiscal_end_tolerance_days: int = Field(ge=0)
    filing_search_days: PositiveInt


class EdgarSettings(StrictModel):
    data_base_url: str = Field(pattern=r"^https://")
    tickers_url: str = Field(pattern=r"^https://")
    archives_base_url: str = Field(pattern=r"^https://")
    timeout_seconds: PositiveFloat
    max_attempts: PositiveInt
    backoff_base_seconds: float = Field(ge=0)
    earnings_release_item: str
    cache_ttl_seconds: EdgarCacheTtl
    financials: EdgarFinancials
    archive: EdgarArchive


class FredCacheTtl(StrictModel):
    observations: int = Field(ge=0)


class FredSettings(HttpSourceSettings):
    cache_ttl_seconds: FredCacheTtl


class CboeCacheTtl(StrictModel):
    vix_history: int = Field(ge=0)


class CboeSettings(HttpSourceSettings):
    """CBOE: дневная история VIX (E2d) — без ключа."""

    user_agent: str = Field(min_length=1)
    cache_ttl_seconds: CboeCacheTtl


class LlmSettings(StrictModel):
    model: str = Field(min_length=1)
    effort: Literal["low", "medium", "high", "xhigh", "max"]
    max_tokens: PositiveInt
    max_attempts: PositiveInt


class RedisSettings(StrictModel):
    timeout_seconds: PositiveFloat


class Sources(StrictModel):
    redis: RedisSettings
    massive: MassiveSettings
    finnhub: FinnhubSettings
    alphavantage: AlphaVantageSettings
    edgar: EdgarSettings
    fred: FredSettings
    cboe: CboeSettings
    llm: LlmSettings
