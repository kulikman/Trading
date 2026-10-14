"""Цены акции через смены тикера (FB → META, 09.06.2022).

Massive хранит историю под тогдашним тикером, а под нынешним до переименования может быть другая
бумага (до 2022 года «META» — ETF Roundhill). История тикеров берётся из справочника и
используется, только если последняя смена — на нынешний тикер. Иначе (например, у GOOGL в
справочнике одна запись «GOOG» 2015 года — это класс C) — только нынешний тикер, без склейки.
"""

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Literal, Protocol

from adapters.massive.models import Bar, TickerChange


class StockHistorySource(Protocol):
    def aggregates(
        self,
        ticker: str,
        multiplier: int,
        timespan: Literal["day"],
        start: date,
        end: date,
        *,
        adjusted: bool = True,
    ) -> list[Bar]:
        """Свечи."""

    def ticker_changes(self, ticker: str) -> list[TickerChange]:
        """История тикеров бумаги."""


def symbol_periods(current: str, changes: Sequence[TickerChange]) -> list[tuple[date, str]]:
    """Периоды (с какой даты, под каким тикером) по возрастанию; первый период — с date.min."""
    ordered = sorted(changes, key=lambda c: c.date)
    if not ordered or ordered[-1].ticker != current:
        return [(date.min, current)]
    periods = [(date.min, ordered[0].ticker)]
    periods += [(c.date, c.ticker) for c in ordered[1:]]
    return periods


def daily_bars(source: StockHistorySource, ticker: str, start: date, end: date) -> list[Bar]:
    """Дневные свечи без поправки на сплиты за [start, end], склеенные по тикерам периода."""
    periods = symbol_periods(ticker, source.ticker_changes(ticker))
    bars: list[Bar] = []
    for i, (since, symbol) in enumerate(periods):
        until = periods[i + 1][0] - timedelta(days=1) if i + 1 < len(periods) else date.max
        lo, hi = max(start, since), min(end, until)
        if lo <= hi:
            bars += source.aggregates(symbol, 1, "day", lo, hi, adjusted=False)
    return bars


def symbol_on(periods: Sequence[tuple[date, str]], day: date) -> str:
    """Тикер, под которым бумага торговалась в день day."""
    current = periods[0][1]
    for since, symbol in periods:
        if since <= day:
            current = symbol
    return current
