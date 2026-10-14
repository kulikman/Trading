from datetime import UTC, date, datetime, timedelta

import pytest

from backtest.black_swan import Level, level_at_entry, levels, scenarios
from backtest.simulate import Trade
from core.config import load_config
from core.session_guard import next_trading_day

SETTINGS = load_config().thresholds.risk_limits.black_swan  # VIX 20/25/35, рост 20/40%, SPY 2/4/7%
START = date(2025, 3, 3)


def trading_days(count: int) -> list[date]:
    out, day = [START], START
    for _ in range(count - 1):
        day = next_trading_day(day)
        out.append(day)
    return out


def test_vix_levels_upgrade_at_once_and_downgrade_after_two_calm_days() -> None:
    days = trading_days(8)
    vix = dict(zip(days, [15.0, 17.0, 20.0, 23.5, 26.0, 15.0, 15.0, 15.0], strict=True))
    spy = dict.fromkeys(days, 100.0)
    by_day = levels(vix, spy, SETTINGS)
    # рост за день везде < 20%; 20 — жёлтый, 26 — оранжевый; после 26 два спокойных дня — зелёный
    expected = ["green", "green", "yellow", "yellow", "orange", "orange", "green", "green"]
    assert [by_day[d] for d in days] == expected


def test_vix_jump_alone_raises_the_level() -> None:
    days = trading_days(3)
    vix = dict(zip(days, [15.0, 18.5, 15.0], strict=True))  # +23% — оранжевый при VIX < 20
    by_day = levels(vix, dict.fromkeys(days, 100.0), SETTINGS)
    assert [by_day[d] for d in days] == ["green", "orange", "orange"]


def test_spy_one_day_and_window_drops() -> None:
    days = trading_days(7)
    vix = dict.fromkeys(days, 15.0)
    spy = dict(zip(days, [100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 87.0], strict=True))
    by_day = levels(vix, spy, SETTINGS)
    # по 1% в день — однодневный сигнал зелёный, но за 5 дней −5% → оранжевый;
    # последний день −8,4% за день → красный
    assert by_day[days[5]] == "orange"
    assert by_day[days[6]] == "red"


def test_missing_vix_day_is_not_a_signal() -> None:
    days = trading_days(3)
    vix = {days[0]: 15.0, days[2]: 16.0}  # праздник в ряду FRED
    by_day = levels(vix, dict.fromkeys(days, 100.0), SETTINGS)
    assert [by_day[d] for d in days] == ["green", "green", "green"]


def test_level_at_entry_is_previous_close() -> None:
    days = trading_days(2)
    by_day: dict[date, Level] = {days[0]: "red", days[1]: "green"}
    assert level_at_entry(days[1], by_day) == "red"
    assert level_at_entry(None, by_day) is None


def trade(entry_on: date, net: float, risk: float = 100.0) -> Trade:
    return Trade(
        ticker="X",
        report_date=entry_on,
        construction="straddle",
        entry_value=1.0,
        exit_value=1.0,
        exit_reason="time",
        exit_at=datetime.combine(entry_on, datetime.min.time(), tzinfo=UTC) + timedelta(days=1),
        gross_pnl=net,
        costs=0.0,
        risk=risk,
        entry_on=entry_on,
    )


def test_scenarios_count_cut_profits_and_saved_losses() -> None:
    days = trading_days(4)
    by_day: dict[date, Level] = {
        days[0]: "red",
        days[1]: "orange",
        days[2]: "yellow",
        days[3]: "green",
    }
    trades = [
        trade(days[1], 50),
        trade(days[2], -100),
        trade(days[3], 20),
    ]  # уровни: red, orange, yellow
    base, red, red_orange, sized = scenarios(trades, by_day, SETTINGS, risk_per_trade=0.01)
    assert (base.trades, base.vetoed, base.net_pnl) == (3, 0, -30)
    assert (red.vetoed, red.vetoed_winners, red.vetoed_losers, red.net_pnl) == (1, 1, 0, -80)
    assert (red_orange.vetoed, red_orange.vetoed_losers, red_orange.net_pnl) == (2, 1, 20)
    assert sized.net_pnl == pytest.approx(0 * 50 + 0.4 * -100 + 0.7 * 20)
    assert sized.equity_change == pytest.approx((1 - 0.01 * 0.4) * (1 + 0.01 * 0.7 * 0.2) - 1)


def test_report_section_lists_levels_periods_and_scenarios() -> None:
    from backtest.report import render
    from backtest.result import BacktestResult

    config = load_config()
    days = trading_days(5)
    by_day: dict[date, Level] = dict(
        zip(days, ["green", "red", "red", "orange", "green"], strict=True)
    )
    result = BacktestResult(since=days[0], until=days[-1])
    result.trades = [trade(days[2], 50), trade(days[4], -20)]  # уровень накануне: red, orange
    text = render(result, config.thresholds, config.broker.selected_costs, None, by_day)
    assert "## Black Swan" in text
    assert "green — 2, yellow — 0, orange — 1, red — 2" in text
    assert f"Периоды красного уровня: {days[1]:%d.%m.%Y}–{days[2]:%d.%m.%Y}." in text
    assert "| Вето красного | 1 | 1 | 1 | 0 | -20 |" in text
