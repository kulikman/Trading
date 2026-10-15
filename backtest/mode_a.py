"""Сделка режима A по дневным свечам (SPEC §10) — для теневых сделок (T16).

Вход: решение в день T−7 (задача 15:15 ET), лимит по закрытию T−8; исполнение — по закрытию T−7,
если оно не выше лимита (внутридневных цен нет). Стоп 1,5 × ATR(14) по дням до входа:
открытие ниже стопа — выход по открытию, минимум дня ≤ стопа — по стопу. Выход T−1 15:50 —
по закрытию T−1. Размер — риск backtest.risk_per_trade капитала до стопа, как у режима C.
"""

import math
from collections.abc import Sequence
from datetime import date, datetime, time

from adapters.massive.models import Bar
from backtest.mode_c import average_true_range
from backtest.simulate import ExitReason, Trade
from core.config.thresholds import Thresholds
from core.session_guard import ET, to_et
from execution.costs import CostLeg, CostModel, total_cost

EXIT_TIME = time(15, 50)


def mode_a_trade(
    ticker: str,
    report_date: date,
    entry_day: date,
    exit_day: date,
    daily: Sequence[Bar],
    *,
    thresholds: Thresholds,
    costs: CostModel,
    capital: float,
) -> Trade | str:
    """Длинная акция T−7 → T−1; нет цен или лимит не исполнен — строка-причина."""
    rules = thresholds.modes.A
    before = [b for b in daily if to_et(b.start).date() < entry_day]
    entry_bar = next((b for b in daily if to_et(b.start).date() == entry_day), None)
    if not before or entry_bar is None:
        return "no_price"
    if entry_bar.close > before[-1].close:
        return "not_filled"  # лимит по закрытию T−8
    atr = average_true_range(before, rules.atr_period)
    if atr is None:
        return "no_atr"
    entry, distance = entry_bar.close, rules.stop_atr_multiple * atr
    stop = entry - distance
    held = [b for b in daily if entry_day < to_et(b.start).date() <= exit_day]
    if not held or to_et(held[-1].start).date() != exit_day:
        return "open_at_end"
    reason: ExitReason = "time"
    price, at_open, exit_on = held[-1].close, False, exit_day
    for bar in held:
        day = to_et(bar.start).date()
        if bar.open <= stop:
            price, reason, at_open, exit_on = bar.open, "stop", True, day
            break
        if bar.low <= stop:
            price, reason, exit_on = stop, "stop", day
            break
    shares = max(1, math.floor(capital * thresholds.backtest.risk_per_trade / distance))
    entry_cost = total_cost(costs, [_leg(shares, entry)], at_open=False)
    exit_cost = total_cost(costs, [_leg(shares, price)], at_open=at_open)
    return Trade(
        ticker=ticker,
        report_date=report_date,
        construction="mode_a",
        entry_value=entry,
        exit_value=price,
        exit_reason=reason,
        exit_at=datetime.combine(exit_on, time(9, 30) if at_open else EXIT_TIME, tzinfo=ET),
        gross_pnl=(price - entry) * shares,
        costs=entry_cost.total + exit_cost.total,
        risk=shares * distance + entry_cost.total,
        variant="long",
        entry_on=entry_day,
    )


def _leg(shares: int, price: float) -> CostLeg:
    return CostLeg(instrument="stock", quantity=shares, multiplier=1, price=price)
