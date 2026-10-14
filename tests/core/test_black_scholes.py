import math

import pytest

from core.pricing.black_scholes import (
    OptionKind,
    greeks,
    implied_volatility,
    price,
    price_bounds,
)

# Эталон: S = K = 100, T = 1 год, r = 5%, σ = 20% (Hull, «Options, Futures and Other Derivatives»).
S, K, T, R, SIGMA = 100.0, 100.0, 1.0, 0.05, 0.20


def test_reference_prices() -> None:
    assert price("call", S, K, T, R, SIGMA) == pytest.approx(10.4506, abs=1e-4)
    assert price("put", S, K, T, R, SIGMA) == pytest.approx(5.5735, abs=1e-4)


def test_put_call_parity_with_dividend() -> None:
    q = 0.02
    call = price("call", S, 110, 0.5, R, 0.3, q)
    put = price("put", S, 110, 0.5, R, 0.3, q)
    assert call - put == pytest.approx(S * math.exp(-q * 0.5) - 110 * math.exp(-R * 0.5))


def test_reference_greeks() -> None:
    call = greeks("call", S, K, T, R, SIGMA)
    put = greeks("put", S, K, T, R, SIGMA)
    assert call.delta == pytest.approx(0.6368, abs=1e-4)
    assert put.delta == pytest.approx(-0.3632, abs=1e-4)
    assert call.gamma == pytest.approx(0.018762, abs=1e-6) == put.gamma
    assert call.vega == pytest.approx(37.524, abs=1e-3) == put.vega
    assert call.theta == pytest.approx(-6.414, abs=1e-3)
    assert put.theta == pytest.approx(-1.658, abs=1e-3)


def test_greeks_with_dividend_match_finite_differences() -> None:
    args = (S, 95.0, 0.1, R, 0.4, 0.03)
    step = 1e-4
    kinds: tuple[OptionKind, ...] = ("call", "put")
    for kind in kinds:
        g = greeks(kind, *args)
        up = price(kind, S + step, *args[1:])
        down = price(kind, S - step, *args[1:])
        assert g.delta == pytest.approx((up - down) / (2 * step), abs=1e-6)
        later = price(kind, S, 95.0, 0.1 - step, R, 0.4, 0.03)
        assert g.theta == pytest.approx((later - price(kind, *args)) / step, rel=1e-3)


@pytest.mark.parametrize("kind", ["call", "put"])
@pytest.mark.parametrize(
    ("strike", "years", "sigma"), [(100, 1, 0.2), (90, 7 / 365, 0.9), (115, 0.05, 1.5)]
)
def test_implied_volatility_round_trip(
    kind: OptionKind, strike: float, years: float, sigma: float
) -> None:
    value = price(kind, S, strike, years, R, sigma)
    assert implied_volatility(kind, value, S, strike, years, R) == pytest.approx(sigma, abs=1e-6)


@pytest.mark.parametrize(
    ("kind", "option_price"),
    [
        ("call", 0.0),  # ниже внутренней стоимости
        ("call", 100.0),  # не дороже акции
        ("put", 200.0),
        ("call", 1e-12),  # σ ниже IV_LOW
    ],
)
def test_implied_volatility_outside_bounds_is_none(kind: OptionKind, option_price: float) -> None:
    assert implied_volatility(kind, option_price, S, K, 7 / 365, R) is None


def test_implied_volatility_above_ceiling_is_none() -> None:
    almost_spot = price_bounds("call", S, K, 1.0, R)[1] - 1e-9
    assert implied_volatility("call", almost_spot, S, K, 1.0, R) is None


def test_deep_itm_call_price_at_intrinsic_is_none() -> None:
    intrinsic = price_bounds("call", S, 50, 0.1, R)[0]
    assert implied_volatility("call", intrinsic, S, 50, 0.1, R) is None


@pytest.mark.parametrize(
    "bad", [(0, 100, 1, 0.2), (100, 0, 1, 0.2), (100, 100, 0, 0.2), (100, 100, 1, 0)]
)
def test_non_positive_inputs_rejected(bad: tuple[float, float, float, float]) -> None:
    spot, strike, years, sigma = bad
    with pytest.raises(ValueError, match="positive"):
        price("call", spot, strike, years, R, sigma)
