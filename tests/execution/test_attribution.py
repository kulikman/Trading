from datetime import date, datetime

import pytest

from backtest.simulate import LegFill
from core.pricing.black_scholes import price
from core.session_guard import ET
from execution.attribution import OptionContract, attribute, parse_occ, years_until

ENTRY = datetime(2026, 10, 19, 16, 0, tzinfo=ET)
EXIT = datetime(2026, 10, 20, 10, 30, tzinfo=ET)
EXPIRY = date(2026, 10, 23)
RATE = 0.04


def test_parse_occ() -> None:
    assert parse_occ("O:UNH261016C00377500") == OptionContract(
        "UNH", date(2026, 10, 16), "call", 377.5
    )
    assert parse_occ("O:BRK.B261016P00450000") == OptionContract(
        "BRK.B", date(2026, 10, 16), "put", 450.0
    )
    assert parse_occ("GS") is None


def test_stock_is_all_direction() -> None:
    parts = attribute(
        (LegFill("GS", "stock", -1, 10, 1, 100.0, 95.0),),
        scale=2.0,
        spot_entry=None,
        spot_exit=None,
        entry_at=ENTRY,
        exit_at=EXIT,
        rate=RATE,
    )
    assert parts is not None
    assert parts.direction == pytest.approx(100.0)  # продажа 10 акций × 2 × (100 − 95)
    assert (parts.vol, parts.ivcrush) == (0.0, 0.0)


def test_long_straddle_split_sums_to_total() -> None:
    """Акция 100 → 108, IV 80% → 40%: дельта ~0, движение — «волатильность», спад IV — минус."""
    t0, t1 = years_until(EXPIRY, ENTRY), years_until(EXPIRY, EXIT)
    legs = tuple(
        LegFill(
            f"O:NFLX261023{'C' if kind == 'call' else 'P'}00100000",
            "option",
            1,
            1,
            100,
            price(kind, 100.0, 100.0, t0, RATE, 0.8),
            price(kind, 108.0, 100.0, t1, RATE, 0.4),
        )
        for kind in ("call", "put")
    )
    parts = attribute(
        legs, scale=0.5, spot_entry=100.0, spot_exit=108.0, entry_at=ENTRY, exit_at=EXIT, rate=RATE
    )
    assert parts is not None
    total = sum(0.5 * 100 * (leg.exit_price - leg.entry_price) for leg in legs)
    assert parts.direction + parts.vol + parts.ivcrush == pytest.approx(total)
    assert abs(parts.direction) < 0.2 * parts.vol  # дельта стрэддла «у денег» мала (≈ 0,07)
    assert parts.vol > 0  # движение 8% принесло прибыль
    assert parts.ivcrush < 0  # спад IV забрал часть


def test_no_split_without_spot_or_model_price() -> None:
    leg = LegFill("O:NFLX261023C00100000", "option", 1, 1, 100, 5.0, 4.0)
    assert (
        attribute(
            (leg,),
            scale=1,
            spot_entry=None,
            spot_exit=101.0,
            entry_at=ENTRY,
            exit_at=EXIT,
            rate=RATE,
        )
        is None
    )
    below_intrinsic = LegFill(
        "O:NFLX261023C00050000", "option", 1, 1, 100, 1.0, 1.0
    )  # колл 50 при S 100
    assert (
        attribute(
            (below_intrinsic,),
            scale=1,
            spot_entry=100.0,
            spot_exit=100.0,
            entry_at=ENTRY,
            exit_at=EXIT,
            rate=RATE,
        )
        is None
    )
