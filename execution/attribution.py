"""P&L сделки по источникам (T17, SPEC §11 / DASHBOARD §4.6): направление, волатильность, спад IV.

Опционная нога (Блэк–Шоулз, σ входа — из цены входа, σ выхода — из цены выхода):
- спад IV = цена выхода − цена по модели при σ входа (S и время — на выходе);
- направление = дельта входа × (S выхода − S входа);
- волатильность = остаток: движение сверх дельты (гамма) и время (тета) при σ входа.
Сумма трёх = валовой результат ноги; издержки — разница с pnl_total. Акция — всё направление.
σ не определяется (цена вне границ модели) — разбивки нет: None, а не догадка.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal, Protocol

from adapters.massive.models import Bar
from backtest.simulate import LegFill
from core.pricing.black_scholes import greeks, implied_volatility, price
from core.session_guard import ET, to_et

OCC = re.compile(r"^O:(?P<root>[A-Z.]+)(?P<expiry>\d{6})(?P<right>[CP])(?P<strike>\d{8})$")
EXPIRY_CLOSE = time(16, 0)
YEAR_SECONDS = 365 * 24 * 3600


@dataclass(frozen=True)
class OptionContract:
    underlying: str
    expiry: date
    right: Literal["call", "put"]
    strike: float


@dataclass(frozen=True)
class Attribution:
    direction: float
    vol: float
    ivcrush: float


class StockBars(Protocol):
    def aggregates(
        self,
        ticker: str,
        multiplier: int,
        timespan: Literal["day", "minute"],
        start: date,
        end: date,
        *,
        adjusted: bool = True,
    ) -> list[Bar]:
        """Свечи."""


def parse_occ(symbol: str) -> OptionContract | None:
    """O:UNH261016C00377500 → UNH, 16.10.2026, call, 377.5; не опцион — None."""
    match = OCC.match(symbol)
    if match is None:
        return None
    raw = match["expiry"]
    expiry = date(2000 + int(raw[:2]), int(raw[2:4]), int(raw[4:]))
    right: Literal["call", "put"] = "call" if match["right"] == "C" else "put"
    return OptionContract(match["root"], expiry, right, int(match["strike"]) / 1000)


def years_until(expiry: date, moment: datetime) -> float:
    """Время до экспирации (закрытие дня экспирации ET), в годах; не меньше минуты."""
    close = datetime.combine(expiry, EXPIRY_CLOSE, tzinfo=ET)
    return max((close - moment).total_seconds(), 60.0) / YEAR_SECONDS


def attribute(
    legs: Sequence[LegFill],
    *,
    scale: float,
    spot_entry: float | None,
    spot_exit: float | None,
    entry_at: datetime,
    exit_at: datetime,
    rate: float,
) -> Attribution | None:
    """Источники P&L позиции в $ (scale — доля позиции бэктеста у paper)."""
    direction = vol = ivcrush = 0.0
    for leg in legs:
        units = leg.side * leg.quantity * leg.multiplier * scale
        if leg.instrument == "stock":
            direction += units * (leg.exit_price - leg.entry_price)
            continue
        contract = parse_occ(leg.symbol)
        if contract is None or spot_entry is None or spot_exit is None:
            return None
        t0, t1 = years_until(contract.expiry, entry_at), years_until(contract.expiry, exit_at)
        k, right = contract.strike, contract.right
        sigma0 = implied_volatility(right, leg.entry_price, spot_entry, k, t0, rate)
        if sigma0 is None:
            return None
        model_exit = price(right, spot_exit, k, t1, rate, sigma0)
        delta = greeks(right, spot_entry, k, t0, rate, sigma0).delta
        leg_direction = delta * (spot_exit - spot_entry)
        leg_ivcrush = leg.exit_price - model_exit
        leg_total = leg.exit_price - leg.entry_price
        direction += units * leg_direction
        ivcrush += units * leg_ivcrush
        vol += units * (leg_total - leg_direction - leg_ivcrush)
    return Attribution(direction=direction, vol=vol, ivcrush=ivcrush)


class MassiveSpots:
    """Цена акции на момент: последняя минута не позже момента; закрытие дня — дневная свеча."""

    def __init__(self, stocks: StockBars) -> None:
        self._stocks = stocks

    def at(self, ticker: str, moment: datetime) -> float | None:
        day = to_et(moment).date()
        bars = self._stocks.aggregates(ticker, 1, "minute", day, day, adjusted=False)
        before = [b for b in bars if b.start <= moment]
        return before[-1].close if before else None

    def close(self, ticker: str, day: date) -> float | None:
        bars = self._stocks.aggregates(
            ticker, 1, "day", day, day + timedelta(days=1), adjusted=False
        )
        same = [b for b in bars if to_et(b.start).date() == day]
        return same[0].close if same else None
