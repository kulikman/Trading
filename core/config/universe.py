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

    def with_watchlist_additions(
        self, active_tickers: list[str], watchlist: "Universe"
    ) -> "Universe":
        """Возвращает новый Universe с добавленными тикерами из watchlist (не мутирует).

        Для каждого active_ticker ищет компанию в watchlist, добавляет в соответствующий сектор.
        Если сектор уже есть в ядре — расширяет его; если новый — создаёт.
        Тикеры, уже присутствующие в ядре, молча пропускаются.
        """
        if not active_tickers:
            return self

        core_tickers = set(self.tickers())
        watchlist_by_ticker: dict[str, tuple[Company, Sector]] = {
            c.ticker: (c, s) for s in watchlist.sectors for c in s.companies
        }

        sectors_extra: dict[str, list[Company]] = {}
        sector_meta: dict[str, Sector] = {}
        for ticker in active_tickers:
            if ticker in core_tickers:
                continue
            if ticker not in watchlist_by_ticker:
                continue
            company, sector = watchlist_by_ticker[ticker]
            sectors_extra.setdefault(sector.id, []).append(company)
            sector_meta[sector.id] = sector

        if not sectors_extra:
            return self

        core_sector_ids = {s.id for s in self.sectors}
        new_sectors = [
            Sector(
                id=s.id,
                name=s.name,
                key_metrics=s.key_metrics,
                macro_sensitivity=s.macro_sensitivity,
                companies=list(s.companies) + sectors_extra.get(s.id, []),
            )
            for s in self.sectors
        ]
        for sid, companies in sectors_extra.items():
            if sid not in core_sector_ids:
                meta = sector_meta[sid]
                new_sectors.append(
                    Sector(
                        id=meta.id,
                        name=meta.name,
                        key_metrics=meta.key_metrics,
                        macro_sensitivity=meta.macro_sensitivity,
                        companies=companies,
                    )
                )
        return Universe(sectors=new_sectors, peer_edges=list(self.peer_edges))


def _require_unique(items: Sequence[Hashable], what: str) -> None:
    seen: set[Hashable] = set()
    for item in items:
        if item in seen:
            raise ValueError(f"duplicate {what}: {item}")
        seen.add(item)
