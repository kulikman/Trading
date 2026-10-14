"""Режим C в бэктесте (T12b, SPEC §10) — упрощённый: без выручки и guidance (их истории нет).

Вход в день реакции:
- сюрприз EPS по модулю > modes.C.min_eps_surprise; направление — знак сюрприза;
- в decision_time_et (10:30): цена ушла от закрытия накануне в ту же сторону;
- объём первого часа (09:30–10:30) > min_volume_ratio × среднего объёма первого часа за
  volume_lookback_days прошлых торговых дней (полного дня в 10:30 ещё нет — без заглядывания);
- лимит: VWAP первого часа ± max_entry_over_vwap; не исполнен до fill_deadline_et — сделки нет.

Выход (дневные цены): трейлинг-стоп trailing_atr_multiple × ATR(atr_period), пересчёт после
закрытия; закрытие хуже SMA(exit_sma_period); не дольше max_hold_days торговых дней.
ATR — среднее истинного диапазона за период (без сглаживания Уайлдера).
"""

import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Literal

from adapters.massive.models import Bar
from core.config.thresholds import BacktestModeC, ModeC
from core.session_guard import ET, to_et

FIRST_HOUR = (time(9, 30), time(10, 30))
CLOSE_TIME = time(16, 0)
Direction = Literal[1, -1]
NoEntry = Literal[
    "surprise_small", "no_price_confirm", "no_volume_confirm", "no_volume_history", "not_filled"
]


@dataclass(frozen=True)
class Entry:
    direction: Direction
    price: float
    at: datetime


@dataclass(frozen=True)
class Exit:
    price: float
    at: datetime
    reason: Literal["trail_stop", "sma", "max_hold"]


def direction_of(surprise_pct: float | None, rules: ModeC) -> Direction | None:
    """Знак сюрприза EPS, если он по модулю больше порога (сюрприз — в процентах)."""
    if surprise_pct is None or abs(surprise_pct) / 100 <= rules.min_eps_surprise:
        return None
    return 1 if surprise_pct > 0 else -1


def first_hour(bars: Sequence[Bar], day: date) -> tuple[float, float | None]:
    """Объём и VWAP за 09:30–10:30 дня; VWAP — по vw минуты (нет — по цене закрытия)."""
    window = [b for b in bars if _on(b, day) and FIRST_HOUR[0] <= _clock(b) < FIRST_HOUR[1]]
    volume = sum(b.volume for b in window)
    if volume <= 0:
        return 0.0, None
    vwap = sum((b.vwap if b.vwap is not None else b.close) * b.volume for b in window) / volume
    return volume, vwap


def confirm(
    direction: Direction,
    pre_close: float,
    reaction: date,
    minutes: Sequence[Bar],
    history_days: Sequence[date],
    rules: ModeC,
    settings: BacktestModeC,
) -> float | NoEntry:
    """Условия режима C к decision_time_et: цена и объём первого часа; итог — VWAP первого часа.

    Общая для бэктеста и живой стратегии (T16): берутся только минуты до decision_time_et.
    """
    past = [first_hour(minutes, day)[0] for day in history_days]
    past = [v for v in past if v > 0]
    if len(past) < settings.min_volume_history_days:
        return "no_volume_history"
    volume, vwap = first_hour(minutes, reaction)
    before = [b for b in minutes if _on(b, reaction) and _clock(b) < settings.decision_time_et]
    if vwap is None or not before:
        return "no_price_confirm"
    if direction * (before[-1].close - pre_close) <= 0:
        return "no_price_confirm"
    if volume <= rules.min_volume_ratio * statistics.fmean(past):
        return "no_volume_confirm"
    return vwap


def entry_limit(direction: Direction, vwap: float, rules: ModeC) -> float:
    """Лимит входа: VWAP первого часа ± max_entry_over_vwap в сторону сделки."""
    return vwap * (1 + direction * rules.max_entry_over_vwap)


def entry(
    direction: Direction,
    pre_close: float,
    reaction: date,
    minutes: Sequence[Bar],
    history_days: Sequence[date],
    rules: ModeC,
    settings: BacktestModeC,
) -> Entry | NoEntry:
    """Вход в день реакции по правилам режима C или причина, почему его нет."""
    vwap = confirm(direction, pre_close, reaction, minutes, history_days, rules, settings)
    if isinstance(vwap, str):
        return vwap
    limit = entry_limit(direction, vwap, rules)
    window = [
        b
        for b in minutes
        if _on(b, reaction) and settings.decision_time_et <= _clock(b) < settings.fill_deadline_et
    ]
    for bar in window:
        if direction * (bar.open - limit) <= 0:  # открытие минуты уже не хуже лимита
            return Entry(direction, bar.open, bar.start)
        if (direction == 1 and bar.low <= limit) or (direction == -1 and bar.high >= limit):
            return Entry(direction, limit, bar.start)
    return "not_filled"


def average_true_range(bars: Sequence[Bar], period: int) -> float | None:
    """Средний истинный диапазон последних period дней (нужно period + 1 свечей)."""
    if len(bars) < period + 1:
        return None
    ranges = [
        max(cur.high - cur.low, abs(cur.high - prev.close), abs(cur.low - prev.close))
        for prev, cur in zip(bars[-period - 1 : -1], bars[-period:], strict=True)
    ]
    return statistics.fmean(ranges)


def exit_after(position: Entry, daily: Sequence[Bar], entry_day: date, rules: ModeC) -> Exit | None:
    """Выход по дневным свечам; daily — по возрастанию, включая день входа и историю до него.

    None — данных до выхода не хватает (позиция ещё открыта на конце истории).
    """
    history = [b for b in daily if to_et(b.start).date() < entry_day]
    after = [b for b in daily if to_et(b.start).date() >= entry_day]
    atr = average_true_range(history, rules.atr_period)
    if atr is None or not after:
        return None
    side = position.direction
    stop = position.price - side * rules.trailing_atr_multiple * atr
    seen = list(history)
    for held, bar in enumerate(after):
        day = to_et(bar.start).date()
        close_at = datetime.combine(day, CLOSE_TIME, tzinfo=ET)
        if held > 0:  # в день входа позиция открыта после 10:30 — дневной минимум мог быть раньше
            if side * (bar.open - stop) <= 0:
                return Exit(bar.open, datetime.combine(day, time(9, 30), tzinfo=ET), "trail_stop")
            if (side == 1 and bar.low <= stop) or (side == -1 and bar.high >= stop):
                return Exit(stop, close_at, "trail_stop")
        seen.append(bar)
        closes = [b.close for b in seen[-rules.exit_sma_period :]]
        if (
            len(closes) == rules.exit_sma_period
            and side * (bar.close - statistics.fmean(closes)) < 0
        ):
            return Exit(bar.close, close_at, "sma")
        if held >= rules.max_hold_days:
            return Exit(bar.close, close_at, "max_hold")
        atr = average_true_range(seen, rules.atr_period) or atr
        stop = (
            max(stop, bar.close - rules.trailing_atr_multiple * atr)
            if side == 1
            else min(stop, bar.close + rules.trailing_atr_multiple * atr)
        )
    return None


def _on(bar: Bar, day: date) -> bool:
    return to_et(bar.start).date() == day


def _clock(bar: Bar) -> time:
    return to_et(bar.start).time()
