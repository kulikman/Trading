"""Проверка правила Black Swan на сделках бэктеста (T12b): сценарии вето и размеров.

Уровень дня считает core.risk.black_swan; сделка видит уровень на закрытии торгового дня перед
днём входа. Действие уровня (risk_limits.black_swan): жёлтый — размер × 0,7; оранжевый — × 0,4 и
только при уверенности > 80% (уверенности модели в бэктесте нет — сценарий «вето оранжевого»
считается отдельно); красный — новых входов нет.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from backtest.simulate import Trade
from core.config.thresholds import BlackSwan
from core.risk.black_swan import Level, level_at_entry


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
