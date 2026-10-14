"""Модель config/universe.yaml: сектора, компании, граф информаторов."""

from collections.abc import Hashable, Sequence
from typing import Literal, Self

from pydantic import Field, model_validator

from core.config.base import StrictModel

TICKER_PATTERN = r"^[A-Z]{1,5}$"

MacroFeature = Literal["vix", "us10y", "regime"]


class Company(StrictModel):
    ticker: str = Field(pattern=TICKER_PATTERN)
    name: str = Field(min_length=1)
    # Прежние регистранты SEC (реорганизация в холдинг): история подач и XBRL — под их CIK.
    sec_predecessor_ciks: list[int] = Field(default_factory=list)


class Sector(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str = Field(min_length=1)
    key_metrics: list[str] = Field(min_length=1)
    macro_sensitivity: list[MacroFeature]
    companies: list[Company] = Field(min_length=1)


class PeerEdge(StrictModel):
    from_ticker: str = Field(pattern=TICKER_PATTERN)
    to_ticker: str = Field(pattern=TICKER_PATTERN)
    strength: float | None = Field(default=None, ge=-1, le=1)
    lag_days: int | None = Field(default=None, ge=0)
    note: str | None = None


class Universe(StrictModel):
    sectors: list[Sector] = Field(min_length=1)
    peer_edges: list[PeerEdge]

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        _require_unique([s.id for s in self.sectors], "sector id")
        tickers = [c.ticker for s in self.sectors for c in s.companies]
        _require_unique(tickers, "ticker")
        known = set(tickers)
        _require_unique([(e.from_ticker, e.to_ticker) for e in self.peer_edges], "peer edge")
        for edge in self.peer_edges:
            if edge.from_ticker == edge.to_ticker:
                raise ValueError(f"peer edge {edge.from_ticker} → itself")
            for ticker in (edge.from_ticker, edge.to_ticker):
                if ticker not in known:
                    raise ValueError(f"peer edge references {ticker}, which is not in any sector")
        return self

    def tickers(self) -> list[str]:
        """Все тикеры вселенной в порядке секторов."""
        return [c.ticker for s in self.sectors for c in s.companies]

    def sec_predecessor_ciks(self) -> dict[str, list[int]]:
        """Тикер → прежние CIK в SEC (только у компаний, где они есть)."""
        return {
            c.ticker: c.sec_predecessor_ciks
            for s in self.sectors
            for c in s.companies
            if c.sec_predecessor_ciks
        }

    def sector_of(self, ticker: str) -> Sector:
        """Сектор компании; KeyError, если тикера нет во вселенной."""
        for sector in self.sectors:
            if any(c.ticker == ticker for c in sector.companies):
                return sector
        raise KeyError(ticker)


def _require_unique(items: Sequence[Hashable], what: str) -> None:
    seen: set[Hashable] = set()
    for item in items:
        if item in seen:
            raise ValueError(f"duplicate {what}: {item}")
        seen.add(item)
