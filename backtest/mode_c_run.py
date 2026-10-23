"""Прогон упрощённого режима C по архиву (T12b): сделки акцией после подтверждённого сюрприза.

Окно — глубина цен акций (stock_history_days, 5 лет). Размер позиции — риск на сделку
(backtest.risk_per_trade капитала) при стопе trailing_atr_multiple × ATR на входе.
"""

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal, Protocol

from sqlalchemy.orm import Session

from adapters.massive.history import EventDays, stock_closes
from adapters.massive.models import Bar, TickerChange
from adapters.massive.symbols import daily_bars, symbol_on, symbol_periods
from backtest.mode_c import Entry, average_true_range, direction_of, entry, exit_after
from backtest.simulate import LegFill, Trade
from core.config.sources import MassiveHistory
from core.config.thresholds import Thresholds
from core.db.store import earnings_history
from core.session_guard import previous_trading_day, to_et
from execution.costs import CostLeg, CostModel, total_cost

HISTORY_MARGIN_DAYS = 45  # до отчёта нужны 20 дней объёма и 15 дней ATR


class StockData(Protocol):
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

    def ticker_changes(self, ticker: str) -> list[TickerChange]:
        """История тикеров."""


@dataclass
class ModeCResult:
    since: date
    trades: list[Trade] = field(default_factory=list)
    signals: Counter[str] = field(default_factory=Counter)
    skipped: Counter[str] = field(default_factory=Counter)


def run_mode_c(
    db: Session,
    tickers: Sequence[str],
    *,
    thresholds: Thresholds,
    history: MassiveHistory,
    stocks: StockData,
    costs: CostModel,
    capital: float,
    today: date,
) -> ModeCResult:
    """Сделки режима C по всем отчётам компаний в окне цен акций."""
    since = today - timedelta(days=history.stock_history_days)
    result = ModeCResult(since=since)
    rules = thresholds.modes.C
    for ticker in tickers:
        rows = [
            r
            for r in earnings_history(db, ticker, since + timedelta(days=HISTORY_MARGIN_DAYS))
            if r.date_check != "mismatch" and r.report_date < today
        ]
        candidates = []
        for row in rows:
            direction = direction_of(row.eps_surprise_pct, rules)
            result.signals["mode_c" if direction else "mode_c: surprise_small"] += 1
            if direction is not None:
                candidates.append((EventDays.of(row.report_date, row.report_time), direction))
        candidates = [(d, s) for d, s in candidates if d.reaction < today]
        if not candidates:
            continue
        daily = daily_bars(stocks, ticker, since, today)
        closes = stock_closes(daily)
        periods = symbol_periods(ticker, stocks.ticker_changes(ticker))
        for days, direction in candidates:
            outcome = stock_trade(
                ticker, days, direction, daily, closes, periods, stocks, thresholds, costs, capital
            )
            if isinstance(outcome, Trade):
                result.trades.append(outcome)
            else:
                result.skipped[f"mode_c: {outcome}"] += 1
    return result


def stock_trade(
    ticker: str,
    days: EventDays,
    direction: Literal[1, -1],
    daily: Sequence[Bar],
    closes: dict[date, float],
    periods: Sequence[tuple[date, str]],
    stocks: StockData,
    thresholds: Thresholds,
    costs: CostModel,
    capital: float,
    fixed_entry: Entry | None = None,
) -> Trade | str:
    """Сделка режима C по правилам бэктеста; общая для бэктеста и теневых сделок (T16).

    fixed_entry — уже исполненный вход paper-карточки (цена и минута по барам после сигнала):
    выход и результат считаются от него, а не от входа бэктеста (окно лимита — с 10:30).
    """
    rules, settings = thresholds.modes.C, thresholds.backtest.mode_c
    pre_close = closes.get(days.pre)
    if pre_close is None:
        return "no_price"
    position: Entry
    if fixed_entry is not None:
        position = fixed_entry
    else:
        volume_days = previous_days(days.reaction, thresholds.backtest.mode_c.volume_lookback_days)
        minutes = stocks.aggregates(
            symbol_on(periods, days.reaction),
            1,
            "minute",
            volume_days[-1],
            days.reaction,
            adjusted=False,
        )
        found = entry(direction, pre_close, days.reaction, minutes, volume_days, rules, settings)
        if not isinstance(found, Entry):
            return found
        position = found
    before = [b for b in daily if to_et(b.start).date() < days.reaction]
    atr = average_true_range(before, rules.atr_period)
    closed = exit_after(position, daily, days.reaction, rules)
    if atr is None:
        return "no_atr"
    if closed is None:
        return "open_at_end"
    stop_distance = rules.trailing_atr_multiple * atr
    shares = max(1, math.floor(capital * thresholds.backtest.risk_per_trade / stop_distance))
    entry_cost = total_cost(costs, [_leg(shares, position.price)], at_open=False)
    exit_cost = total_cost(costs, [_leg(shares, closed.price)], at_open=to_et(closed.at).hour == 9)
    return Trade(
        ticker=ticker,
        report_date=days.report_date,
        construction="mode_c",
        entry_value=position.price,
        exit_value=closed.price,
        exit_reason=closed.reason,
        exit_at=closed.at,
        gross_pnl=direction * (closed.price - position.price) * shares,
        costs=entry_cost.total + exit_cost.total,
        risk=shares * stop_distance + entry_cost.total,
        variant="long" if direction == 1 else "short",
        entry_on=days.reaction,
        entry_at=position.at,
        legs=(LegFill(ticker, "stock", direction, shares, 1, position.price, closed.price),),
    )


def previous_days(day: date, count: int) -> list[date]:
    """count торговых дней строго до day, от ближнего к дальнему."""
    out = []
    for _ in range(count):
        day = previous_trading_day(day)
        out.append(day)
    return out


def _leg(shares: int, price: float) -> CostLeg:
    return CostLeg(instrument="stock", quantity=shares, multiplier=1, price=price)
