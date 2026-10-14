"""Результат прогона бэктеста (T12): сделки, сигналы, пропуски."""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from backtest.simulate import Trade


@dataclass
class BacktestResult:
    since: date
    until: date
    trades: list[Trade] = field(default_factory=list)
    signals: Counter[str] = field(default_factory=Counter)
    skipped: Counter[str] = field(default_factory=Counter)
    tickers: int = 0
