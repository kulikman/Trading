"""Отчёт бэктеста (T12) в Markdown: параметры, итоги по конструкциям, выходы, пропуски, сделки."""

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import date

from backtest.black_swan import scenarios
from backtest.metrics import Metrics, metrics
from backtest.mode_c_run import ModeCResult
from backtest.result import BacktestResult
from backtest.simulate import Trade
from core.config.broker import CostSettings
from core.config.thresholds import Thresholds
from core.risk.black_swan import ORDER, Level
from core.session_guard import ET

CONSTRUCTION_NAMES = {
    "straddle": "Стрэддл (покупка)",
    "iron_condor": "Iron condor (продажа)",
    "mode_c": "Режим C (акция)",
}
REASON_NAMES = {
    "stop": "стоп",
    "target": "цель",
    "time": "время (11:00)",
    "trail_stop": "трейлинг-стоп",
    "sma": "закрытие хуже SMA",
    "max_hold": "срок удержания",
}
SIDE_NAMES = {"long": "покупка", "short": "продажа"}


def render(
    result: BacktestResult,
    thresholds: Thresholds,
    costs: CostSettings,
    mode_c: ModeCResult | None = None,
    swan: Mapping[date, Level] | None = None,
) -> str:
    """Полный отчёт: стратегии на move_ratio и (если передан) упрощённый режим C."""
    bt = thresholds.backtest
    rules = thresholds.constructions
    straddles = [t for t in result.trades if t.construction == "straddle"]
    segments = [(CONSTRUCTION_NAMES["straddle"], straddles)]
    for basis in bt.compare_condor_stops:
        condors = [
            t for t in result.trades if t.construction == "iron_condor" and t.variant == basis
        ]
        segments.append((_trade_name("iron_condor", basis, thresholds), condors))
    totals = [
        (
            f"**Все сделки** (кондор: {_stop_label(basis, thresholds)})",
            [t for t in result.trades if t.variant in ("", basis)],
        )
        for basis in bt.compare_condor_stops
    ]
    rows = [(name, _metrics(trades, thresholds)) for name, trades in [*segments, *totals]]
    lines = [
        f"# Бэктест стратегий на move_ratio — {result.until:%d.%m.%Y}",
        "",
        (
            f"Окно: отчёты с {result.since:%d.%m.%Y} по {result.until:%d.%m.%Y} "
            f"(цены опционов — 2 года). Компаний с сигналами: {result.tickers}."
        ),
        "",
        "## Правила",
        "",
        (
            f"- Сигнал: средний |движение| последних {bt.signal_lookback_reports} отчётов компании "
            f"(не меньше {bt.signal_min_reports}) / implied move текущего отчёта; "
            "только прошлые отчёты."
        ),
        (
            f"- Стрэддл при ratio > {rules.straddle.min_move_ratio}: ATM, "
            "вход по закрытию накануне; "
            f"стоп −{rules.straddle.stop_premium_loss:.0%} премии, "
            f"цель +{rules.straddle.target_premium_gain:.0%}."
        ),
        (
            f"- Iron condor при ratio < {rules.iron_condor.max_move_ratio}: продажа на "
            f"{rules.iron_condor.short_implied_moves:g} implied move, защита на "
            f"{rules.iron_condor.wing_implied_moves:g}; цель — "
            f"{rules.iron_condor.target_premium_share:.0%} премии; стоп — сравниваются толкования: "
            + "; ".join(_stop_label(b, thresholds) for b in bt.compare_condor_stops)
            + "."
        ),
        f"- Выход — по минутам в день реакции, не позже {bt.exit_time_et:%H:%M} ET.",
        (
            f"- Издержки: ${costs.commission_per_contract} за контракт, спред "
            f"{costs.assumed_spread_option:.0%} цены опциона (допущение, котировок нет), "
            f"проскальзывание {costs.open_slippage:.1%} в первые {bt.open_slippage_minutes} минут."
        ),
        (
            f"- Кривая капитала: риск {bt.risk_per_trade:.0%} капитала на сделку "
            "(риск = максимальный убыток с издержками входа)."
        ),
        "",
        "## Сигналы",
        "",
        _counter_line(result.signals),
        "",
        "## Итоги",
        "",
        (
            "| Конструкция | Сделок | Выигрыш | EV на $1 риска | Медиана | P&L, $ | Издержки, $ | "
            "Sharpe | Просадка | Капитал | Правило 30 |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    lines += [_row(name, m) for name, m in rows]
    lines += [
        "",
        (
            "P&L и издержки — на один контракт каждой ноги. «Капитал» — изменение при риске "
            f"{bt.risk_per_trade:.0%} на сделку."
        ),
        "",
        "## Причины выхода",
        "",
    ]
    for name, trades in segments:
        reasons = Counter(REASON_NAMES[t.exit_reason] for t in trades)
        lines.append(f"- {name}: {_counter_line(reasons)}")
    lines += ["", "## Пропущено (нет данных)", "", _counter_line(result.skipped), ""]
    lines += _trades_table(result.trades, thresholds)
    if mode_c is not None:
        lines += _mode_c_section(mode_c, thresholds)
    if swan is not None:
        groups = [(name, group) for name, group in segments]
        if mode_c is not None:
            groups.append(("Режим C", mode_c.trades))
        lines += _black_swan_section(groups, swan, thresholds)
    lines += [
        "",
        "## Ограничения",
        "",
        "- Около 2 лет цен опционов: выводы по сегментам меньше 30 сделок — предварительные.",
        (
            "- Вход — по цене закрытия накануне, выход — по цене последней сделки минуты; "
            "котировок нет, спред — допущение."
        ),
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


def _trades_table(trades: Sequence[Trade], thresholds: Thresholds) -> list[str]:
    lines = [
        "## Сделки",
        "",
        (
            "| Отчёт | Компания | Конструкция | Вход | Выход | Причина | Время выхода ET | "
            "P&L, $ | На $1 риска |"
        ),
        "|---|---|---|---:|---:|---|---|---:|---:|",
    ]
    for t in sorted(trades, key=lambda x: (x.report_date, x.ticker, x.variant)):
        lines.append(
            f"| {t.report_date:%d.%m.%Y} | {t.ticker} | "
            f"{_trade_name(t.construction, t.variant, thresholds)} | "
            f"{t.entry_value:.2f} | {t.exit_value:.2f} | {REASON_NAMES[t.exit_reason]} | "
            f"{t.exit_at.astimezone(ET):%H:%M} | {t.net_pnl:,.0f} | {t.return_on_risk:+.2f} |"
        )
    return lines


def _stop_label(basis: str, thresholds: Thresholds) -> str:
    multiple = thresholds.constructions.iron_condor.stop_premium_multiple
    if basis == "cost":
        return f"стоп при выкупе {multiple:g}× премии"
    return f"стоп при убытке {multiple:g}× премии"


def _trade_name(construction: str, variant: str, thresholds: Thresholds) -> str:
    name = CONSTRUCTION_NAMES[construction]
    if construction == "mode_c":
        return f"{name}, {SIDE_NAMES[variant]}"
    return f"{name}, {_stop_label(variant, thresholds)}" if variant else name


def _mode_c_section(mc: ModeCResult, thresholds: Thresholds) -> list[str]:
    rules, settings = thresholds.modes.C, thresholds.backtest.mode_c
    trades = mc.trades
    segments = [
        ("Режим C, все сделки", trades),
        ("Режим C, покупка", [t for t in trades if t.variant == "long"]),
        ("Режим C, продажа", [t for t in trades if t.variant == "short"]),
    ]
    years = sorted({t.report_date.year for t in trades})
    segments += [(f"Режим C, {y}", [t for t in trades if t.report_date.year == y]) for y in years]
    lines = [
        "",
        "## Режим C (упрощённый)",
        "",
        (
            f"Окно: отчёты с {mc.since:%d.%m.%Y} (цены акций — 5 лет). Без выручки и guidance — "
            "их истории в бесплатных источниках нет (решение заказчика 14.10.2026)."
        ),
        "",
        (
            f"- Вход: |сюрприз EPS| > {rules.min_eps_surprise:.0%}; к "
            f"{settings.decision_time_et:%H:%M} ET цена ушла от закрытия накануне в сторону "
            f"сюрприза; объём 09:30–10:30 > {rules.min_volume_ratio:g}× среднего за "
            f"{settings.volume_lookback_days} дней; лимит VWAP первого часа ± "
            f"{rules.max_entry_over_vwap:.1%}, не исполнен до {settings.fill_deadline_et:%H:%M} — "
            "сделки нет."
        ),
        (
            f"- Выход: трейлинг {rules.trailing_atr_multiple:g} × ATR({rules.atr_period}) "
            f"после закрытия, закрытие хуже SMA({rules.exit_sma_period}), не дольше "
            f"{rules.max_hold_days} торговых дней."
        ),
        (
            f"- Размер: риск {thresholds.backtest.risk_per_trade:.0%} капитала при стопе "
            f"{rules.trailing_atr_multiple:g} × ATR; "
            f"спред акции {settings.assumed_spread_stock:.2%} "
            "цены — допущение (котировок нет)."
        ),
        "",
        "Сигналы: " + _counter_line(mc.signals) + ".",
        "",
        (
            "| Сегмент | Сделок | Выигрыш | EV на $1 риска | Медиана | P&L, $ | Издержки, $ | "
            "Sharpe | Просадка | Капитал | Правило 30 |"
        ),
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    lines += [_row(name, _metrics(group, thresholds)) for name, group in segments]
    reasons = Counter(REASON_NAMES[t.exit_reason] for t in trades)
    lines += [
        "",
        f"P&L — при риске {thresholds.backtest.risk_per_trade:.0%} капитала на сделку.",
        "",
        f"Причины выхода: {_counter_line(reasons)}.",
        "",
        f"Пропущено: {_counter_line(mc.skipped)}.",
        "",
    ]
    lines += _trades_table(trades, thresholds)
    return lines


def _black_swan_section(
    groups: Sequence[tuple[str, Sequence[Trade]]],
    by_day: Mapping[date, Level],
    thresholds: Thresholds,
) -> list[str]:
    settings = thresholds.risk_limits.black_swan
    rule = settings.rule
    counts = Counter(by_day.values())
    days = sorted(by_day)
    lines = [
        "",
        "## Black Swan",
        "",
        (
            f"Правило (стартовые гипотезы, решение заказчика 13.10.2026): VIX ≥ "
            f"{rule.vix_levels.yellow:g} / {rule.vix_levels.orange:g} / {rule.vix_levels.red:g}; "
            f"рост VIX за день ≥ {rule.vix_jump.orange:.0%} / {rule.vix_jump.red:.0%}; падение SPY "
            f"за день или {rule.spy_drop_window_days} дней ≥ "
            f"{rule.spy_drop.yellow or 0:.0%} / {rule.spy_drop.orange:.0%} / "
            f"{rule.spy_drop.red:.0%}. "
            f"Понижение — после {rule.calm_days_to_downgrade} спокойных дней. Сделка видит уровень "
            "на закрытии дня перед входом."
        ),
        "",
        (
            f"Дней с {days[0]:%d.%m.%Y} по {days[-1]:%d.%m.%Y}: "
            + ", ".join(f"{level} — {counts.get(level, 0)}" for level in ORDER)
            + "."
        )
        if days
        else "Нет данных об уровне.",
        "",
        "Периоды красного уровня: " + (", ".join(_periods(by_day, "red")) or "нет") + ".",
        "",
        (
            "Уверенности модели в бэктесте нет, поэтому условие оранжевого «только при "
            "уверенности > 80%» проверяется как сценарий «вето красного и оранжевого»."
        ),
    ]
    for name, trades in groups:
        if not trades:
            continue
        lines += [
            "",
            f"### {name}",
            "",
            (
                "| Сценарий | Сделок | Вето | Отрезано прибыльных | Спасено убыточных | "
                "P&L, $ | Капитал | Просадка |"
            ),
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for s in scenarios(trades, by_day, settings, thresholds.backtest.risk_per_trade):
            lines.append(
                f"| {s.name} | {s.trades} | {s.vetoed} | {s.vetoed_winners} | "
                f"{s.vetoed_losers} | {s.net_pnl:,.0f} | {s.equity_change:+.1%} | "
                f"{s.max_drawdown:.1%} |"
            )
    return lines


def _periods(by_day: Mapping[date, Level], level: Level) -> list[str]:
    """Непрерывные отрезки дней с уровнем level: «дд.мм.гггг–дд.мм.гггг»."""
    out: list[str] = []
    start: date | None = None
    previous: date | None = None
    for day in sorted(by_day):
        if by_day[day] == level:
            start = start or day
            previous = day
        elif start is not None and previous is not None:
            out.append(f"{start:%d.%m.%Y}–{previous:%d.%m.%Y}")
            start = None
    if start is not None and previous is not None:
        out.append(f"{start:%d.%m.%Y}–{previous:%d.%m.%Y}")
    return out


def _counter_line(counter: Counter[str]) -> str:
    return ", ".join(f"{k} — {v}" for k, v in sorted(counter.items())) or "нет"


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


def _num(value: float | None, spec: str) -> str:
    return "—" if value is None else format(value, spec)
