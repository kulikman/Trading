import math
from datetime import date, datetime, time, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from adapters.broker.factory import create_cost_model
from adapters.massive.history import EventDays, stock_closes
from adapters.massive.models import Bar, TickerChange
from backtest.mode_c import Entry
from backtest.mode_c_run import run_mode_c, stock_trade
from backtest.report import render
from backtest.result import BacktestResult
from backtest.simulate import Trade
from core.config import load_config
from core.db.store import save_reported_earnings, sync_universe
from core.domain.earnings import ReportedEarnings
from core.session_guard import ET, next_trading_day, previous_trading_day
from execution.costs import BrokerCostModel

CONFIG = load_config()
TODAY = date(2026, 10, 14)
REACTION = date(2025, 10, 22)  # BMO: накануне — 21.10
SMALL = date(2025, 7, 22)  # сюрприз 2% — не сигнал


def bar(day: date, hh: int, mm: int, close: float, volume: float, **kw: float) -> Bar:
    start = datetime.combine(day, time(hh, mm), tzinfo=ET)
    return Bar.model_validate(
        {
            "o": kw.get("open", close),
            "h": kw.get("high", close),
            "l": kw.get("low", close),
            "c": close,
            "v": volume,
            "vw": kw.get("vwap", close),
            "t": start.timestamp() * 1000,
        }
    )


def trading_days_before(day: date, count: int) -> list[date]:
    out = []
    for _ in range(count):
        day = previous_trading_day(day)
        out.append(day)
    return list(reversed(out))


class Stocks:
    def __init__(self) -> None:
        self.minute_calls: list[tuple[str, date, date]] = []

    def ticker_changes(self, ticker: str) -> list[TickerChange]:
        return []

    def aggregates(
        self, ticker: str, multiplier: int, timespan: str, start: date, end: date, **kwargs: Any
    ) -> list[Bar]:
        if timespan == "minute":
            self.minute_calls.append((ticker, start, end))
            past = [bar(d, 9, 31, 100, 1000) for d in trading_days_before(REACTION, 20)]
            return [
                *past,
                bar(REACTION, 9, 31, 105, 3000, vwap=105),
                bar(REACTION, 10, 29, 106, 100),
                bar(REACTION, 10, 31, 106, 100, low=105, high=107),
            ]
        day1 = next_trading_day(REACTION)
        flat = [bar(d, 0, 0, 100, 1e6, high=101, low=99) for d in trading_days_before(REACTION, 60)]
        return [
            *flat,
            bar(REACTION, 0, 0, 106, 1e6, high=107, low=104),
            bar(day1, 0, 0, 100, 1e6, open=100, high=101, low=99),  # гэп вниз — стоп по открытию
        ]


@pytest.fixture
def archive(session: Session) -> Session:
    sync_universe(session, CONFIG.universe)
    save_reported_earnings(
        session,
        [
            ReportedEarnings(
                ticker="NFLX",
                report_date=REACTION,
                report_time="BMO",
                fiscal_period_end=date(2025, 9, 30),
                eps_surprise_pct=10.0,
            ),
            ReportedEarnings(
                ticker="NFLX",
                report_date=SMALL,
                report_time="BMO",
                fiscal_period_end=date(2025, 6, 30),
                eps_surprise_pct=2.0,
            ),
        ],
    )
    return session


def test_mode_c_trade_by_hand(archive: Session) -> None:
    stocks = Stocks()
    costs = BrokerCostModel(
        CONFIG.broker.selected_costs.model_copy(update={"assumed_spread_stock": 0.0005})
    )
    result = run_mode_c(
        archive,
        ["NFLX"],
        thresholds=CONFIG.thresholds,
        history=CONFIG.sources.massive.history,
        stocks=stocks,
        costs=costs,
        capital=100_000,
        today=TODAY,
    )
    assert dict(result.signals) == {"mode_c": 1, "mode_c: surprise_small": 1}
    [trade] = result.trades
    vwap = (105 * 3000 + 106 * 100) / 3100
    entry = vwap * 1.003
    shares = math.floor(100_000 * 0.01 / (2 * 2.0))  # риск 1% при стопе 2 × ATR(14) = 4 → 250 акций
    assert (trade.construction, trade.variant, trade.exit_reason) == (
        "mode_c",
        "long",
        "trail_stop",
    )
    assert trade.entry_value == pytest.approx(entry)
    assert trade.exit_value == 100  # открытие следующего дня ниже стопа
    assert trade.gross_pnl == pytest.approx((100 - entry) * shares)
    entry_costs = 250 * 0.005 + entry * 0.0005 / 2 * 250
    exit_costs = 250 * 0.005 + 100 * 0.0005 / 2 * 250 + 100 * 0.001 * 250  # выход на открытии
    assert trade.costs == pytest.approx(entry_costs + exit_costs)
    assert trade.risk == pytest.approx(250 * 4 + entry_costs)
    assert stocks.minute_calls == [("NFLX", date(2025, 9, 24), REACTION)]  # 20 торговых дней назад

    text = render(
        BacktestResult(since=TODAY - timedelta(days=730), until=TODAY),
        CONFIG.thresholds,
        CONFIG.broker.selected_costs,
        result,
    )
    assert "## Режим C (упрощённый)" in text
    assert "| Режим C, покупка | 1 | 0% |" in text
    assert "| Режим C, 2025 | 1 |" in text
    assert "трейлинг-стоп — 1" in text


def test_mismatched_and_future_reports_are_skipped(archive: Session) -> None:
    result = run_mode_c(
        archive,
        ["NFLX"],
        thresholds=CONFIG.thresholds,
        history=CONFIG.sources.massive.history,
        stocks=Stocks(),
        costs=create_cost_model(CONFIG.broker),
        capital=100_000,
        today=REACTION,  # реакция ещё не наступила
    )
    assert result.trades == []


def test_trade_from_a_fixed_entry_does_not_look_for_the_backtest_entry() -> None:
    stocks = Stocks()
    daily = stocks.aggregates("NFLX", 1, "day", date(2025, 8, 1), TODAY)
    fixed = Entry(1, 104.0, datetime(2025, 10, 22, 10, 46, tzinfo=ET))
    trade = stock_trade(
        "NFLX",
        EventDays.of(REACTION, "BMO"),
        1,
        daily,
        stock_closes(daily),
        [],
        stocks,
        CONFIG.thresholds,
        create_cost_model(CONFIG.broker),
        100_000,
        fixed_entry=fixed,
    )
    assert isinstance(trade, Trade)
    assert (trade.entry_value, trade.entry_at) == (104.0, fixed.at)  # вход карточки, не бэктеста
    assert stocks.minute_calls == []  # минутные бары для поиска входа не запрашиваются
