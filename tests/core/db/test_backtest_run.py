from datetime import time

import pytest
from sqlalchemy.orm import Session

from adapters.broker.factory import create_cost_model
from backtest.report import render
from backtest.result import BacktestResult
from backtest.run import run_backtest
from core.config import load_config
from core.session_guard import ET
from execution.costs import CostModel
from tests.core.db.test_exit_data import (  # noqa: F401 — фикстура archive используется pytest
    STRADDLE_DAY,
    TODAY,
    Options,
    Stocks,
    archive,
    loader,
)

CONFIG = load_config()


def backtest(db: Session, costs: CostModel | None) -> BacktestResult:
    return run_backtest(
        db,
        ["NFLX"],
        thresholds=CONFIG.thresholds,
        history=CONFIG.sources.massive.history,
        stocks=Stocks(),
        costs=costs,
        today=TODAY,
    )


def test_backtest_refuses_to_run_without_cost_model(archive: Session) -> None:  # noqa: F811
    with pytest.raises(ValueError, match="CostModel"):
        backtest(archive, None)


def test_backtest_end_to_end_from_archive(archive: Session) -> None:  # noqa: F811
    loader(Options()).load(archive, "NFLX")  # минутные цены ног и ноги кондора — в архиве
    result = backtest(archive, create_cost_model(CONFIG.broker))
    assert dict(result.signals) == {"straddle": 1, "iron_condor": 1}
    [trade] = result.trades
    # стрэддл: вход 4 + 4 = 8; 09:31 — 6 (не стоп 4 и не цель 16), 11:00 — 5 → выход по времени
    assert (trade.report_date, trade.construction, trade.exit_reason) == (
        STRADDLE_DAY,
        "straddle",
        "time",
    )
    assert (trade.entry_value, trade.exit_value) == (8.0, 5.0)
    assert trade.exit_at.astimezone(ET).time() == time(11, 0)
    assert trade.gross_pnl == pytest.approx(-300.0)
    # кондор: все ноги по 2,0 накануне → премии нет
    assert dict(result.skipped) == {"iron_condor: no_credit": 1}

    text = render(result, CONFIG.thresholds, CONFIG.broker.selected_costs)
    assert "| Стрэддл (покупка) | 1 | 0% |" in text
    assert "мало данных" in text
    assert "iron_condor: no_credit — 1" in text
    assert "| 21.10.2025 | NFLX | Стрэддл (покупка) | 8.00 | 5.00 | время (11:00) | 11:00 |" in text


def test_no_signals_means_empty_result(session: Session) -> None:
    result = backtest(session, create_cost_model(CONFIG.broker))
    assert (result.trades, result.tickers) == ([], 0)
