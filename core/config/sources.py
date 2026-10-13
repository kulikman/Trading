"""Модель config/sources.yaml: технические параметры адаптеров."""

from pydantic import Field

from core.config.base import PositiveFloat, PositiveInt, StrictModel


class MassivePageLimit(StrictModel):
    aggregates: int = Field(gt=0, le=50000)
    option_contracts: int = Field(gt=0, le=1000)
    option_chain: int = Field(gt=0, le=250)


class MassiveCacheTtl(StrictModel):
    aggregates: int = Field(ge=0)
    last_quote: int = Field(ge=0)
    snapshot: int = Field(ge=0)
    option_contracts: int = Field(ge=0)
    option_chain: int = Field(ge=0)


class MassiveImpliedMove(StrictModel):
    expiration_lookahead_days: PositiveInt
    max_plausible_iv: PositiveFloat


class MassiveSettings(StrictModel):
    base_url: str = Field(pattern=r"^https://")
    timeout_seconds: PositiveFloat
    max_attempts: PositiveInt
    backoff_base_seconds: float = Field(ge=0)
    max_pages: PositiveInt
    page_limit: MassivePageLimit
    cache_ttl_seconds: MassiveCacheTtl
    implied_move: MassiveImpliedMove


class RedisSettings(StrictModel):
    timeout_seconds: PositiveFloat


class Sources(StrictModel):
    redis: RedisSettings
    massive: MassiveSettings
