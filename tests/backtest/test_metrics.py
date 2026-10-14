import math
import statistics
from datetime import UTC, date, datetime, timedelta

import pytest

from backtest.metrics import metrics
from backtest.simulate import Trade

START = datetime(2025, 1, 2, 15, tzinfo=UTC)


def trade(days: int, net: float, risk: float = 100.0) -> Trade:
    return Trade(
        ticker="X",
        report_date=date(2025, 1, 1),
        construction="straddle",
        entry_value=1.0,
        exit_value=1.0,
        exit_reason="time",
        exit_at=START + timedelta(days=days),
        gross_pnl=net + 2.0,
        costs=2.0,
        risk=risk,
    )


def test_metrics_by_hand() -> None:
    trades = [trade(0, 50), trade(100, -100), trade(200, 50), trade(365, 100)]  # r = 0,5 −1 0,5 1
    result = metrics(trades, risk_per_trade=0.01, min_obs=30)
    assert (result.trades, result.wins, result.win_rate) == (4, 3, 0.75)
    assert result.mean_return == pytest.approx(0.25)
    assert result.median_return == pytest.approx(0.5)
    assert (result.net_pnl, result.costs, result.gross_pnl) == (100, 8, 108)
    returns = [0.5, -1, 0.5, 1]
    mean, std = 0.25, 0.8660254037844386
    assert result.sharpe == pytest.approx(mean / std * math.sqrt(4 / (365 / 365.25)))
    assert std == pytest.approx(statistics.stdev(returns))
    equity = [1.005, 1.005 * 0.99, 1.005 * 0.99 * 1.005, 1.005 * 0.99 * 1.005 * 1.01]
    assert result.equity_change == pytest.approx(equity[-1] - 1)
    assert result.max_drawdown == pytest.approx(0.01)  # от пика 1,005 до 0,99495
    assert result.enough is False  # меньше 30 сделок


def test_short_span_does_not_inflate_sharpe() -> None:
    trades = [trade(0, 50), trade(1, -20), trade(2, 30)]
    result = metrics(trades, risk_per_trade=0.01, min_obs=3)
    returns = [0.5, -0.2, 0.3]
    expected = 0.2 / statistics.stdev(returns) * math.sqrt(3 / 0.25)
    assert result.sharpe == pytest.approx(expected)
    assert result.enough is True


def test_empty_and_flat_sets() -> None:
    empty = metrics([], risk_per_trade=0.01, min_obs=30)
    assert (empty.trades, empty.win_rate, empty.mean_return, empty.sharpe) == (0, None, None, None)
    flat = metrics([trade(0, 10), trade(5, 10)], risk_per_trade=0.01, min_obs=30)
    assert flat.sharpe is None  # нет разброса — Sharpe не определён
