"""Black Swan (решение заказчика 13.10.2026): детерминированный уровень рыночного риска.

Уровень дня — худший из сигналов на закрытии:
- VIX (FRED VIXCLS) ≥ порогов жёлтый / оранжевый / красный;
- рост VIX за день ≥ порогов оранжевый / красный;
- падение SPY за день или за spy_drop_window_days дней ≥ порогов.
Повышение — сразу; понижение — после calm_days_to_downgrade дней подряд с сигналом ниже
текущего уровня (до наибольшего сигнала этих дней).

Сделка видит уровень на закрытии торгового дня перед днём входа — то, что известно до решения.
Действие уровня (risk_limits.black_swan): жёлтый — размер × 0,7; оранжевый — × 0,4 и только при
уверенности > 80% (уверенности модели в бэктесте нет — сценарий «вето оранжевого» считается
отдельно); красный — новых входов нет.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from backtest.simulate import Trade
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


@dataclass(frozen=True)
class Scenario:
    name: str
    trades: int
    vetoed: int
    vetoed_winners: int  # отрезанная прибыль
    vetoed_losers: int  # спасённые убытки
    net_pnl: float  # с учётом множителей размера
    equity_change: float
    max_drawdown: float


def scenario(
    name: str,
    trades: Sequence[Trade],
    entry_levels: Sequence[Level | None],
    multipliers: Mapping[Level, float],
    risk_per_trade: float,
) -> Scenario:
    """Кривая капитала, если размер сделки умножить на множитель её уровня (0 — вето)."""
    weights = [multipliers.get(level or "green", 1.0) for level in entry_levels]
    order = sorted(range(len(trades)), key=lambda i: trades[i].exit_at)
    equity, peak, drawdown = 1.0, 1.0, 0.0
    for i in order:
        equity *= 1 + risk_per_trade * weights[i] * trades[i].return_on_risk
        peak = max(peak, equity)
        drawdown = max(drawdown, 1 - equity / peak)
    vetoed = [t for t, w in zip(trades, weights, strict=True) if w == 0]
    return Scenario(
        name=name,
        trades=len(trades) - len(vetoed),
        vetoed=len(vetoed),
        vetoed_winners=sum(t.net_pnl > 0 for t in vetoed),
        vetoed_losers=sum(t.net_pnl <= 0 for t in vetoed),
        net_pnl=sum(t.net_pnl * w for t, w in zip(trades, weights, strict=True)),
        equity_change=equity - 1,
        max_drawdown=drawdown,
    )


def scenarios(
    trades: Sequence[Trade],
    by_day: Mapping[date, Level],
    settings: BlackSwan,
    risk_per_trade: float,
) -> list[Scenario]:
    """Без правила; вето красного; вето красного и оранжевого; полное правило размеров."""
    entry_levels = [level_at_entry(t.entry_on, by_day) for t in trades]
    sizes: dict[Level, float] = {
        "yellow": settings.yellow.size_multiplier,
        "orange": settings.orange.size_multiplier,
        "red": settings.red.size_multiplier,
    }
    return [
        scenario("Без правила", trades, entry_levels, {}, risk_per_trade),
        scenario("Вето красного", trades, entry_levels, {"red": 0.0}, risk_per_trade),
        scenario(
            "Вето красного и оранжевого",
            trades,
            entry_levels,
            {"red": 0.0, "orange": 0.0},
            risk_per_trade,
        ),
        scenario(
            "Размеры по уровню (× 0,7 / 0,4 / 0)", trades, entry_levels, sizes, risk_per_trade
        ),
    ]
