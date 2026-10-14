"""Модель Блэка–Шоулза для европейских опционов: цена, IV из цены, греки.

Нужна там, где источник даёт только цены (исторические опционы Massive, T10). Американский
опцион на акцию без дивиденда до экспирации стоит как европейский (колл) и близко к нему (пут
на коротком сроке), поэтому для недельных опционов на отчёт приближение допустимо.

Единицы: время — в годах, ставки и волатильность — доли (0.04, 0.35). Вега — на 1.00 волатильности,
тета — за год.
"""

import math
from dataclasses import dataclass
from typing import Literal

OptionKind = Literal["call", "put"]

IV_LOW = 1e-4
IV_HIGH = 5.0
IV_TOLERANCE = 1e-10
IV_MAX_ITERATIONS = 200


@dataclass(frozen=True)
class Greeks:
    delta: float
    gamma: float
    vega: float
    theta: float


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _check(spot: float, strike: float, years: float, sigma: float) -> None:
    if spot <= 0 or strike <= 0 or years <= 0 or sigma <= 0:
        raise ValueError("spot, strike, years and sigma must be positive")


def _d1_d2(
    spot: float, strike: float, years: float, rate: float, sigma: float, dividend: float
) -> tuple[float, float]:
    root = sigma * math.sqrt(years)
    d1 = (math.log(spot / strike) + (rate - dividend + sigma * sigma / 2) * years) / root
    return d1, d1 - root


def price(
    kind: OptionKind,
    spot: float,
    strike: float,
    years: float,
    rate: float,
    sigma: float,
    dividend: float = 0.0,
) -> float:
    """Цена опциона."""
    _check(spot, strike, years, sigma)
    d1, d2 = _d1_d2(spot, strike, years, rate, sigma, dividend)
    spot_disc = spot * math.exp(-dividend * years)
    strike_disc = strike * math.exp(-rate * years)
    if kind == "call":
        return spot_disc * _norm_cdf(d1) - strike_disc * _norm_cdf(d2)
    return strike_disc * _norm_cdf(-d2) - spot_disc * _norm_cdf(-d1)


def price_bounds(
    kind: OptionKind, spot: float, strike: float, years: float, rate: float, dividend: float = 0.0
) -> tuple[float, float]:
    """Безарбитражные границы цены: (внутренняя стоимость, максимум)."""
    spot_disc = spot * math.exp(-dividend * years)
    strike_disc = strike * math.exp(-rate * years)
    if kind == "call":
        return max(spot_disc - strike_disc, 0.0), spot_disc
    return max(strike_disc - spot_disc, 0.0), strike_disc


def implied_volatility(
    kind: OptionKind,
    option_price: float,
    spot: float,
    strike: float,
    years: float,
    rate: float,
    dividend: float = 0.0,
) -> float | None:
    """IV из цены бисекцией (цена монотонна по σ). Цена вне границ или вне [IV_LOW, IV_HIGH] → None.

    None — «не определяется», а не ошибка: у цены последней сделки такое бывает (сделка давно,
    спред широкий). Значение не угадываем.
    """
    _check(spot, strike, years, 1.0)
    low_price, high_price = price_bounds(kind, spot, strike, years, rate, dividend)
    if not low_price < option_price < high_price:
        return None
    low, high = IV_LOW, IV_HIGH
    if price(kind, spot, strike, years, rate, low, dividend) > option_price:
        return None
    if price(kind, spot, strike, years, rate, high, dividend) < option_price:
        return None
    for _ in range(IV_MAX_ITERATIONS):
        middle = (low + high) / 2
        if price(kind, spot, strike, years, rate, middle, dividend) < option_price:
            low = middle
        else:
            high = middle
        if high - low < IV_TOLERANCE:
            break
    return (low + high) / 2


def greeks(
    kind: OptionKind,
    spot: float,
    strike: float,
    years: float,
    rate: float,
    sigma: float,
    dividend: float = 0.0,
) -> Greeks:
    """Дельта, гамма, вега (на 1.00 σ), тета (за год)."""
    _check(spot, strike, years, sigma)
    d1, d2 = _d1_d2(spot, strike, years, rate, sigma, dividend)
    growth = math.exp(-dividend * years)
    discount = math.exp(-rate * years)
    root = math.sqrt(years)
    gamma = growth * _norm_pdf(d1) / (spot * sigma * root)
    vega = spot * growth * _norm_pdf(d1) * root
    decay = -spot * growth * _norm_pdf(d1) * sigma / (2 * root)
    if kind == "call":
        delta = growth * _norm_cdf(d1)
        theta = (
            decay
            - rate * strike * discount * _norm_cdf(d2)
            + dividend * spot * growth * _norm_cdf(d1)
        )
    else:
        delta = growth * (_norm_cdf(d1) - 1)
        theta = (
            decay
            + rate * strike * discount * _norm_cdf(-d2)
            - dividend * spot * growth * _norm_cdf(-d1)
        )
    return Greeks(delta=delta, gamma=gamma, vega=vega, theta=theta)
