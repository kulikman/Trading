"""Уровень Black Swan (решение заказчика 13.10.2026): детерминированный уровень рыночного риска.

Уровень дня — худший из сигналов на закрытии: VIX (FRED VIXCLS) ≥ порогов жёлтый / оранжевый /
красный; рост VIX за день; падение SPY за день или за spy_drop_window_days дней. Повышение —
сразу; понижение — после calm_days_to_downgrade дней подряд с сигналом ниже текущего уровня.
Используют агент «Макро» (regime) и бэктест (сценарии вето).
"""

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Literal

from core.config.thresholds import BlackSwan, LevelThresholds
from core.session_guard import previous_trading_day

Level = Literal["green", "yellow", "orange", "red"]
ORDER: tuple[Level, ...] = ("green", "yellow", "orange", "red")


def _rank(level: Level) -> int:
    return ORDER.index(level)


def _by_threshold(value: float, thresholds: LevelThresholds) -> Level:
    if value >= thresholds.red:
        return "red"
    if value >= thresholds.orange:
        return "orange"
    if thresholds.yellow is not None and value >= thresholds.yellow:
        return "yellow"
    return "green"


def daily_signal(
    day: date,
    vix: Mapping[date, float],
    spy: Mapping[date, float],
    days: Sequence[date],
    settings: BlackSwan,
) -> Level:
    """Худший сигнал дня; days — торговые дни по возрастанию, day в них."""
    rule = settings.rule
    index = days.index(day)
    signals: list[Level] = []
    if day in vix:
        signals.append(_by_threshold(vix[day], rule.vix_levels))
        if index > 0 and days[index - 1] in vix:
            jump = vix[day] / vix[days[index - 1]] - 1
            signals.append(_by_threshold(jump, rule.vix_jump))
    if day in spy:
        for window in (1, rule.spy_drop_window_days):
            if index >= window and days[index - window] in spy:
                drop = 1 - spy[day] / spy[days[index - window]]
                signals.append(_by_threshold(drop, rule.spy_drop))
    return max(signals, key=_rank) if signals else "green"


def levels(
    vix: Mapping[date, float], spy: Mapping[date, float], settings: BlackSwan
) -> dict[date, Level]:
    """Уровень на закрытии каждого торгового дня (дни — где есть цена SPY)."""
    days = sorted(spy)
    result: dict[date, Level] = {}
    current: Level = "green"
    calm: list[Level] = []
    for day in days:
        signal = daily_signal(day, vix, spy, days, settings)
        if _rank(signal) >= _rank(current):
            current, calm = signal, []
        else:
            calm.append(signal)
            if len(calm) >= settings.rule.calm_days_to_downgrade:
                current, calm = max(calm, key=_rank), []
        result[day] = current
    return result


def level_at_entry(entry_day: date | None, by_day: Mapping[date, Level]) -> Level | None:
    """Уровень, известный перед входом: закрытие предыдущего торгового дня. Нет дня — None."""
    return None if entry_day is None else by_day.get(previous_trading_day(entry_day))
