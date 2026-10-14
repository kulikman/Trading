"""Метрики бэктеста (T12): точность, EV на $1 риска после издержек, Sharpe, максимальная просадка.

- Доходность сделки — чистый P&L / риск (максимальный убыток с издержками входа).
- EV на $1 риска — средняя доходность сделки.
- Sharpe — среднее / стандартное отклонение доходности × √(сделок в год); год — по датам
  первой и последней сделки, не короче min_years (иначе короткий период раздувает оценку).
- Просадка — по кривой капитала при фиксированном риске на сделку (risk_per_trade капитала),
  сделки — по времени выхода.
- Правило 30 (SPEC §9): сегмент меньше min_obs сделок помечается «мало данных».
"""

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass

from backtest.simulate import Trade

MIN_YEARS = 0.25


@dataclass(frozen=True)
class Metrics:
    trades: int
    wins: int
    mean_return: float | None
    median_return: float | None
    gross_pnl: float
    costs: float
    net_pnl: float
    sharpe: float | None
    max_drawdown: float
    equity_change: float
    enough: bool

    @property
    def win_rate(self) -> float | None:
        return self.wins / self.trades if self.trades else None


def metrics(trades: Sequence[Trade], *, risk_per_trade: float, min_obs: int) -> Metrics:
    """Метрики набора сделок (одна конструкция или все вместе)."""
    ordered = sorted(trades, key=lambda t: t.exit_at)
    returns = [t.return_on_risk for t in ordered]
    equity, peak, drawdown = 1.0, 1.0, 0.0
    for value in returns:
        equity *= 1 + risk_per_trade * value
        peak = max(peak, equity)
        drawdown = max(drawdown, 1 - equity / peak)
    return Metrics(
        trades=len(ordered),
        wins=sum(t.net_pnl > 0 for t in ordered),
        mean_return=statistics.fmean(returns) if returns else None,
        median_return=statistics.median(returns) if returns else None,
        gross_pnl=sum(t.gross_pnl for t in ordered),
        costs=sum(t.costs for t in ordered),
        net_pnl=sum(t.net_pnl for t in ordered),
        sharpe=_sharpe(ordered, returns),
        max_drawdown=drawdown,
        equity_change=equity - 1,
        enough=len(ordered) >= min_obs,
    )


def _sharpe(ordered: Sequence[Trade], returns: Sequence[float]) -> float | None:
    if len(returns) < 2:
        return None
    spread = statistics.stdev(returns)
    if spread == 0:
        return None
    span_days = (ordered[-1].exit_at - ordered[0].exit_at).total_seconds() / 86400
    years = max(span_days / 365.25, MIN_YEARS)
    return statistics.fmean(returns) / spread * math.sqrt(len(returns) / years)
