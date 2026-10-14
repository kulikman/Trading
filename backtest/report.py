"""Отчёт бэктеста (T12a) в Markdown: параметры, итоги по конструкциям, выходы, пропуски, сделки."""

from collections import Counter
from collections.abc import Sequence

from backtest.metrics import Metrics, metrics
from backtest.run import BacktestResult
from backtest.simulate import Trade
from core.config.broker import CostSettings
from core.config.thresholds import Thresholds
from core.session_guard import ET

CONSTRUCTION_NAMES = {"straddle": "Стрэддл (покупка)", "iron_condor": "Iron condor (продажа)"}
REASON_NAMES = {"stop": "стоп", "target": "цель", "time": "время (11:00)"}


def render(result: BacktestResult, thresholds: Thresholds, costs: CostSettings) -> str:
    """Полный отчёт."""
    bt = thresholds.backtest
    rules = thresholds.constructions
    by_construction = {
        name: [t for t in result.trades if t.construction == name] for name in CONSTRUCTION_NAMES
    }
    rows = [
        (CONSTRUCTION_NAMES[name], _metrics(trades, thresholds))
        for name, trades in by_construction.items()
    ]
    rows.append(("**Все сделки**", _metrics(result.trades, thresholds)))
    lines = [
        f"# Бэктест стратегий на move_ratio — {result.until:%d.%m.%Y}",
        "",
        f"Окно: отчёты с {result.since:%d.%m.%Y} по {result.until:%d.%m.%Y} "
        f"(цены опционов — 2 года). Компаний с сигналами: {result.tickers}.",
        "",
        "## Правила",
        "",
        f"- Сигнал: средний |движение| последних {bt.signal_lookback_reports} отчётов компании "
        f"(не меньше {bt.signal_min_reports}) / implied move текущего отчёта; "
        "только прошлые отчёты.",
        f"- Стрэддл при ratio > {rules.straddle.min_move_ratio}: ATM, вход по закрытию накануне; "
        f"стоп −{rules.straddle.stop_premium_loss:.0%} премии, "
        f"цель +{rules.straddle.target_premium_gain:.0%}.",
        f"- Iron condor при ratio < {rules.iron_condor.max_move_ratio}: продажа на "
        f"{rules.iron_condor.short_implied_moves:g} implied move, защита на "
        f"{rules.iron_condor.wing_implied_moves:g}; "
        f"стоп — выкуп {rules.iron_condor.stop_premium_multiple:g}× "
        f"премии, цель — {rules.iron_condor.target_premium_share:.0%} премии.",
        f"- Выход — по минутам в день реакции, не позже {bt.exit_time_et:%H:%M} ET.",
        f"- Издержки: ${costs.commission_per_contract} за контракт, спред "
        f"{costs.assumed_spread_option:.0%} цены опциона (допущение, котировок нет), "
        f"проскальзывание {costs.open_slippage:.1%} в первые {bt.open_slippage_minutes} минут.",
        f"- Кривая капитала: риск {bt.risk_per_trade:.0%} капитала на сделку "
        "(риск = максимальный убыток с издержками входа).",
        "",
        "## Сигналы",
        "",
        _counter_line(result.signals),
        "",
        "## Итоги",
        "",
        "| Конструкция | Сделок | Выигрыш | EV на $1 риска | Медиана | P&L, $ | Издержки, $ | "
        "Sharpe | Просадка | Капитал | Правило 30 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    lines += [_row(name, m) for name, m in rows]
    lines += [
        "",
        "P&L и издержки — на один контракт каждой ноги. «Капитал» — изменение при риске "
        f"{bt.risk_per_trade:.0%} на сделку.",
        "",
        "## Причины выхода",
        "",
    ]
    for name, trades in by_construction.items():
        reasons = Counter(REASON_NAMES[t.exit_reason] for t in trades)
        lines.append(f"- {CONSTRUCTION_NAMES[name]}: {_counter_line(reasons)}")
    lines += ["", "## Пропущено (нет данных)", "", _counter_line(result.skipped), ""]
    lines += _trades_table(result.trades)
    lines += [
        "",
        "## Ограничения",
        "",
        "- Около 2 лет цен опционов: выводы по сегментам меньше 30 сделок — предварительные.",
        "- Вход — по цене закрытия накануне, выход — по цене последней сделки минуты; "
        "котировок нет, спред — допущение.",
        "- Стоп и цель проверяются по закрытию минуты; движение внутри минуты не учитывается.",
        "- Отчёты с датой, не совпавшей с 8-K (`date_check = mismatch`), исключены.",
    ]
    return "\n".join(lines) + "\n"


def _metrics(trades: Sequence[Trade], thresholds: Thresholds) -> Metrics:
    return metrics(
        trades,
        risk_per_trade=thresholds.backtest.risk_per_trade,
        min_obs=thresholds.models.min_segment_obs,
    )


def _row(name: str, m: Metrics) -> str:
    return (
        f"| {name} | {m.trades} | {_pct(m.win_rate)} | {_num(m.mean_return, '+.3f')} | "
        f"{_num(m.median_return, '+.3f')} | {m.net_pnl:,.0f} | {m.costs:,.0f} | "
        f"{_num(m.sharpe, '.2f')} | {m.max_drawdown:.1%} | {m.equity_change:+.1%} | "
        f"{'достаточно' if m.enough else 'мало данных'} |"
    )


def _trades_table(trades: Sequence[Trade]) -> list[str]:
    lines = [
        "## Сделки",
        "",
        "| Отчёт | Компания | Конструкция | Вход | Выход | Причина | Время выхода ET | "
        "P&L, $ | На $1 риска |",
        "|---|---|---|---:|---:|---|---|---:|---:|",
    ]
    for t in sorted(trades, key=lambda x: (x.report_date, x.ticker)):
        lines.append(
            f"| {t.report_date:%d.%m.%Y} | {t.ticker} | {CONSTRUCTION_NAMES[t.construction]} | "
            f"{t.entry_value:.2f} | {t.exit_value:.2f} | {REASON_NAMES[t.exit_reason]} | "
            f"{t.exit_at.astimezone(ET):%H:%M} | {t.net_pnl:,.0f} | {t.return_on_risk:+.2f} |"
        )
    return lines


def _counter_line(counter: Counter[str]) -> str:
    return ", ".join(f"{k} — {v}" for k, v in sorted(counter.items())) or "нет"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


def _num(value: float | None, spec: str) -> str:
    return "—" if value is None else format(value, spec)
