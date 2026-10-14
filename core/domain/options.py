"""Дневная цена опционного контракта — архив для бэктеста (T10).

Источник даёт историю только за скользящее окно (Massive — 2 года), поэтому скачанное
хранится у нас.
"""

from datetime import date

from pydantic import Field

from core.domain.base import DomainModel
from core.domain.types import OptionType


class OptionDailyBar(DomainModel):
    option_ticker: str  # O:NFLX241018C00700000
    day: date  # торговый день, ET
    underlying: str
    expiration: date
    strike: float = Field(gt=0)
    option_type: OptionType
    open: float = Field(ge=0)
    high: float = Field(ge=0)
    low: float = Field(ge=0)
    close: float = Field(ge=0)
    volume: float = Field(ge=0)
    vwap: float | None = Field(default=None, ge=0)
    transactions: int | None = Field(default=None, ge=0)
