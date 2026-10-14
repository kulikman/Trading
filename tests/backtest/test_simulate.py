from datetime import UTC, date, datetime, time

import pytest

from adapters.broker.factory import create_cost_model
from backtest.simulate import Leg, Trade, position_path, simulate
from core.config import load_config
from core.domain.options import OptionMinuteBar
from core.session_guard import ET

CONFIG = load_config()
COSTS = create_cost_model(
    CONFIG.broker
)  # manual: $0.65 за контракт, спред 3% цены, 0,1% на открытии
RULES = CONFIG.thresholds.constructions
DAY = date(2025, 10, 22)
OPEN = datetime.combine(DAY, time(9, 30), tzinfo=ET)


def at(hh: int, mm: int) -> datetime:
    return datetime.combine(DAY, time(hh, mm), tzinfo=ET)


def bars(ticker: str, *points: tuple[datetime, float]) -> list[OptionMinuteBar]:
    return [
        OptionMinuteBar(
            option_ticker=ticker, minute=m.astimezone(UTC), open=c, high=c, low=c, close=c, volume=1
        )
        for m, c in points
    ]


STRADDLE = [Leg("C", 1, 5.0), Leg("P", 1, 5.0)]


def run_straddle(minutes: dict[str, list[OptionMinuteBar]]) -> Trade | str:
    return simulate(
        "NFLX",
        date(2025, 10, 21),
        "straddle",
        STRADDLE,
        minutes,
        rules=RULES,
        costs=COSTS,
        session_open=OPEN,
        open_slippage_minutes=5,
    )


def test_straddle_target_with_costs_computed_by_hand() -> None:
    minutes = {
        "C": bars("C", (at(9, 31), 6.0), (at(9, 40), 14.0)),
        "P": bars("P", (at(9, 31), 4.0), (at(9, 40), 6.5)),
    }
    trade = run_straddle(minutes)
    assert isinstance(trade, Trade)
    assert (trade.exit_reason, trade.exit_value) == ("target", 20.5)  # 20,5 ≥ 2 × 10
    assert trade.exit_at == at(9, 40)
    assert trade.gross_pnl == pytest.approx(1050.0)  # (20,5 − 10) × 100
    # вход: комиссия 2 × 0,65 + половина спреда 2 × 5 × 1,5% × 100 = 1,30 + 15 = 16,30
    # выход (после 09:35 — без проскальзывания): 1,30 + (14 + 6,5) × 1,5% × 100 = 1,30 + 30,75
    assert trade.costs == pytest.approx(16.30 + 32.05)
    assert trade.risk == pytest.approx(1000 + 16.30)  # премия + издержки входа
    assert trade.return_on_risk == pytest.approx((1050 - 48.35) / 1016.30)


def test_straddle_stop_in_first_minutes_pays_open_slippage() -> None:
    minutes = {"C": bars("C", (at(9, 32), 2.0)), "P": bars("P", (at(9, 32), 2.5))}
    trade = run_straddle(minutes)
    assert isinstance(trade, Trade)
    assert (trade.exit_reason, trade.exit_value) == ("stop", 4.5)  # ≤ 10 × (1 − 0,5)
    exit_spread = (2.0 + 2.5) * 0.015 * 100
    slippage = (2.0 + 2.5) * 0.001 * 100
    assert trade.costs == pytest.approx(16.30 + 1.30 + exit_spread + slippage)


def test_straddle_time_exit_at_last_price() -> None:
    minutes = {
        "C": bars("C", (at(9, 45), 6.0), (at(10, 59), 7.0)),
        "P": bars("P", (at(9, 50), 5.0)),
    }
    trade = run_straddle(minutes)
    assert isinstance(trade, Trade)
    assert (trade.exit_reason, trade.exit_value, trade.exit_at) == ("time", 12.0, at(10, 59))


def test_leg_without_trades_means_no_exit_price() -> None:
    assert run_straddle({"C": bars("C", (at(9, 31), 6.0))}) == "no_exit_price"


CONDOR = [Leg("LP", 1, 1.0), Leg("SP", -1, 2.0), Leg("SC", -1, 2.5), Leg("LC", 1, 1.0)]


def run_condor(minutes: dict[str, list[OptionMinuteBar]], legs: list[Leg] = CONDOR) -> Trade | str:
    return simulate(
        "NFLX",
        date(2025, 10, 21),
        "iron_condor",
        legs,
        minutes,
        rules=RULES,
        costs=COSTS,
        session_open=OPEN,
        open_slippage_minutes=5,
        width=10.0,
    )


def condor_minutes(lp: float, sp: float, sc: float, lc: float) -> dict[str, list[OptionMinuteBar]]:
    return {t: bars(t, (at(9, 45), p)) for t, p in (("LP", lp), ("SP", sp), ("SC", sc), ("LC", lc))}


def test_condor_target_keeps_half_the_credit() -> None:
    trade = run_condor(condor_minutes(0.2, 0.6, 0.8, 0.2))  # выкуп 1,0 ≤ 2,5 × 50%
    assert isinstance(trade, Trade)
    assert (trade.exit_reason, trade.entry_value, trade.exit_value) == ("target", 2.5, 1.0)
    assert trade.gross_pnl == pytest.approx(150.0)  # (2,5 − 1,0) × 100
    entry_costs = 4 * 0.65 + (1.0 + 2.0 + 2.5 + 1.0) * 0.015 * 100
    assert trade.risk == pytest.approx((10 - 2.5) * 100 + entry_costs)


def test_condor_stop_at_twice_the_credit() -> None:
    trade = run_condor(condor_minutes(0.5, 3.5, 2.5, 0.5))  # выкуп 5,0 ≥ 2 × 2,5
    assert isinstance(trade, Trade)
    assert (trade.exit_reason, trade.exit_value) == ("stop", 5.0)
    assert trade.gross_pnl == pytest.approx(-250.0)


def test_condor_without_credit_is_skipped() -> None:
    legs = [Leg("LP", 1, 3.0), Leg("SP", -1, 1.0), Leg("SC", -1, 1.0), Leg("LC", 1, 3.0)]
    assert run_condor(condor_minutes(1, 1, 1, 1), legs) == "no_credit"


def test_position_path_waits_for_all_legs_and_forward_fills() -> None:
    minutes = {
        "C": bars("C", (at(9, 31), 6.0), (at(9, 34), 7.0)),
        "P": bars("P", (at(9, 33), 4.0)),
    }
    path = position_path(STRADDLE, minutes)
    assert [(m.astimezone(ET).time(), v) for m, v in path] == [
        (time(9, 33), 10.0),
        (time(9, 34), 11.0),
    ]
