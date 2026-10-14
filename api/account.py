"""Полоса счёта и раздел «Счёт» (DASHBOARD.md §3, §4.6): все расчёты здесь, не на фронте.

Источник баланса в MVP (ручной брокер, §5): стартовый капитал из thresholds.yaml + итоги
закрытых сделок. Нереализованный P&L, стоимость открытых позиций и их риск до стопов появятся
с исполнителем (T17): пока есть открытые карточки, эти поля — «нет данных», а не ноль.
«Сезон» — текущий календарный квартал по ET (отчёты идут поквартально).
"""

import math
import statistics
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta

from pydantic import BaseModel

from api.format import Num, count, day, empty, money, percent, ratio
from api.trades_data import ClosedTrade, OpenCard
from core.config.thresholds import Thresholds
from core.session_guard import is_regular_session, is_trading_day, previous_trading_day, to_et

TRADING_DAYS_PER_YEAR = 252
NO_TRADES = "нет сделок"
AFTER_EXECUTOR = "нет данных до исполнителя (T17)"

type Metric = Callable[[Sequence[ClosedTrade]], Num]


class AccountBar(BaseModel):
    mode: str
    is_available: bool
    message: str | None = None
    balance: Num | None = None
    free: Num | None = None
    in_trades: Num | None = None
    in_trades_share: Num | None = None
    pnl_today: Num | None = None
    pnl_today_share: Num | None = None
    pnl_month: Num | None = None
    pnl_month_share: Num | None = None
    risk: Num | None = None
    worst_drawdown: Num | None = None
    drawdown_threshold: Num | None = None
    refresh_seconds: int


class PeriodRow(BaseModel):
    period: str
    pnl: Num
    pnl_share: Num
    trades: Num
    win_rate: Num


class MetricRow(BaseModel):
    metric: str
    season: Num
    all_time: Num


class CurvePoint(BaseModel):
    day: str
    balance: Num


class Criterion(BaseModel):
    criterion: str
    display: str  # «СДЕЛОК 34/50»
    is_met: bool
    tone: str


class AccountSummary(BaseModel):
    mode: str
    is_available: bool
    message: str | None = None
    periods: list[PeriodRow] = []
    metrics: list[MetricRow] = []
    curve: list[CurvePoint] = []
    curve_message: str | None = None
    path_to_real: list[Criterion] = []


def account_bar(
    mode: str,
    trades: Sequence[ClosedTrade],
    open_cards: Sequence[OpenCard],
    *,
    capital: float | None,
    thresholds: Thresholds,
    now: datetime,
) -> AccountBar:
    refresh = _refresh_seconds(thresholds, now)
    if capital is None:
        return AccountBar(
            mode=mode, is_available=False, message="Счёт Real не подключён", refresh_seconds=refresh
        )
    today = to_et(now).date()
    balance = capital + sum(t.pnl for t in trades)
    pnl_today = _pnl_since(trades, today)
    pnl_month = _pnl_since(trades, today.replace(day=1))
    limit = thresholds.risk_limits.drawdown.manual_review
    if open_cards:
        in_trades, share, risk, worst = (empty(AFTER_EXECUTOR) for _ in range(4))
        free = empty(AFTER_EXECUTOR)
    else:
        in_trades, share = money(0), percent(0)
        free, risk = money(balance), percent(0)
        worst = percent(current_drawdown(trades, capital))
        if worst.value is not None and worst.value >= limit:
            worst = worst.model_copy(update={"tone": "action"})
    return AccountBar(
        mode=mode,
        is_available=True,
        balance=money(balance),
        free=free,
        in_trades=in_trades,
        in_trades_share=share,
        pnl_today=money(pnl_today, signed=True),
        pnl_today_share=percent(pnl_today / balance, signed=True),
        pnl_month=money(pnl_month, signed=True),
        pnl_month_share=percent(pnl_month / balance, signed=True),
        risk=risk,
        worst_drawdown=worst,
        drawdown_threshold=percent(limit, digits=0),
        refresh_seconds=refresh,
    )


def account_summary(
    mode: str,
    trades: Sequence[ClosedTrade],
    *,
    capital: float | None,
    thresholds: Thresholds,
    now: datetime,
    first_card_at: datetime | None,
) -> AccountSummary:
    if capital is None:
        return AccountSummary(mode=mode, is_available=False, message="Счёт Real не подключён")
    today = to_et(now).date()
    season_start = date(today.year, 3 * ((today.month - 1) // 3) + 1, 1)
    periods = [
        ("сегодня", today),
        ("неделя", today - timedelta(days=today.weekday())),
        ("месяц", today.replace(day=1)),
        ("сезон", season_start),
        ("всё время", date.min),
    ]
    season = [t for t in trades if _close_day(t) >= season_start]
    curve = equity_curve(trades, capital)
    return AccountSummary(
        mode=mode,
        is_available=True,
        periods=[_period(name, trades, start, capital) for name, start in periods],
        metrics=_metrics(season, trades, capital, thresholds, today),
        curve=[CurvePoint(day=day(d), balance=money(b)) for d, b in curve],
        curve_message=None if curve else NO_TRADES,
        path_to_real=_path_to_real(trades, capital, thresholds, today, first_card_at),
    )


def equity_curve(trades: Sequence[ClosedTrade], capital: float) -> list[tuple[date, float]]:
    """Баланс на конец каждого дня, в который закрывались сделки."""
    balance, points = capital, {}
    for trade in sorted(trades, key=lambda t: t.closed_at):
        balance += trade.pnl
        points[_close_day(trade)] = balance
    return sorted(points.items())


def max_drawdown(trades: Sequence[ClosedTrade], capital: float) -> float:
    peak, worst, balance = capital, 0.0, capital
    for trade in sorted(trades, key=lambda t: t.closed_at):
        balance += trade.pnl
        peak = max(peak, balance)
        worst = max(worst, (peak - balance) / peak)
    return worst


def current_drawdown(trades: Sequence[ClosedTrade], capital: float) -> float:
    balance = capital + sum(t.pnl for t in trades)
    peak = max([capital, *(b for _, b in equity_curve(trades, capital))])
    return (peak - balance) / peak


def daily_sharpe(
    trades: Sequence[ClosedTrade], capital: float, today: date, min_days: int
) -> float | None:
    """Sharpe по дневным доходностям баланса (торговые дни с первой сделки), годовой."""
    if not trades:
        return None
    by_day: dict[date, float] = {}
    for trade in trades:
        by_day[_close_day(trade)] = by_day.get(_close_day(trade), 0.0) + trade.pnl
    days, current = [], today
    first = min(by_day)
    while current >= first:
        if is_trading_day(current):
            days.append(current)
        current = previous_trading_day(current)
    days.reverse()
    if len(days) < min_days:
        return None
    balance, returns = capital, []
    for d in days:
        pnl = by_day.get(d, 0.0)
        returns.append(pnl / balance)
        balance += pnl
    spread = statistics.pstdev(returns)
    if spread == 0:
        return None
    return statistics.fmean(returns) / spread * math.sqrt(TRADING_DAYS_PER_YEAR)


def _metrics(
    season: Sequence[ClosedTrade],
    everything: Sequence[ClosedTrade],
    capital: float,
    thresholds: Thresholds,
    today: date,
) -> list[MetricRow]:
    min_days = thresholds.dashboard.sharpe_min_days

    def sharpe(ts: Sequence[ClosedTrade]) -> Num:
        return ratio(daily_sharpe(ts, capital, today, min_days))

    def total(ts: Sequence[ClosedTrade]) -> Num:
        return percent(_sum(ts) / capital, signed=True)

    def profit_factor(ts: Sequence[ClosedTrade]) -> Num:
        lost = -sum(_losses(ts))
        return ratio(sum(_wins(ts)) / lost if lost else None)

    named: list[tuple[str, Metric]] = [
        ("Доходность", total),
        ("Win rate", lambda ts: percent(len(_wins(ts)) / len(ts))),
        ("Средняя прибыль", lambda ts: money(_mean(_wins(ts)))),
        ("Средний убыток", lambda ts: money(_mean(_losses(ts)))),
        ("Profit factor", profit_factor),
        ("Ожидаемая прибыль на сделку", lambda ts: money(_sum(ts) / len(ts), signed=True)),
        ("Sharpe", sharpe),
        ("Максимальная просадка", lambda ts: percent(max_drawdown(ts, capital))),
        ("Текущая просадка", lambda ts: percent(current_drawdown(ts, capital))),
    ]
    named += [(f"P&L режим {m}", _by_mode(m)) for m in ("A", "B", "C")]
    named += [
        (f"P&L источник: {label}", _by_source(attr))
        for label, attr in (
            ("направление", "pnl_direction"),
            ("волатильность", "pnl_vol"),
            ("спад IV", "pnl_ivcrush"),
        )
    ]
    rows = [
        MetricRow(metric=name, season=_guard(f, season), all_time=_guard(f, everything))
        for name, f in named
    ]
    rows.append(
        MetricRow(metric="Издержки", season=empty(AFTER_EXECUTOR), all_time=empty(AFTER_EXECUTOR))
    )
    return rows


def _guard(compute: Metric, trades: Sequence[ClosedTrade]) -> Num:
    return compute(trades) if trades else empty(NO_TRADES)


def _by_mode(mode: str) -> Metric:
    return lambda ts: money(sum(t.pnl for t in ts if t.mode == mode), signed=True)


def _by_source(attr: str) -> Metric:
    return lambda ts: money(sum(getattr(t, attr) or 0.0 for t in ts), signed=True)


def _wins(trades: Sequence[ClosedTrade]) -> list[float]:
    return [t.pnl for t in trades if t.pnl > 0]


def _losses(trades: Sequence[ClosedTrade]) -> list[float]:
    return [t.pnl for t in trades if t.pnl < 0]


def _sum(trades: Sequence[ClosedTrade]) -> float:
    return sum(t.pnl for t in trades)


def _path_to_real(
    trades: Sequence[ClosedTrade],
    capital: float,
    thresholds: Thresholds,
    today: date,
    first_card_at: datetime | None,
) -> list[Criterion]:
    rule = thresholds.dashboard.path_to_real
    sharpe = daily_sharpe(trades, capital, today, thresholds.dashboard.sharpe_min_days)
    drawdown = max_drawdown(trades, capital)
    days = 0 if first_card_at is None else (today - to_et(first_card_at).date()).days
    items = [
        ("СДЕЛОК", f"{len(trades)}/{rule.min_trades}", len(trades) >= rule.min_trades),
        (
            "SHARPE",
            f"{ratio(sharpe).display}/{ratio(rule.min_sharpe, 1).display}",
            sharpe is not None and sharpe > rule.min_sharpe,
        ),
        (
            "ПРОСАДКА",
            f"{percent(drawdown, digits=0).display}/{percent(rule.max_drawdown, digits=0).display}",
            bool(trades) and drawdown < rule.max_drawdown,
        ),
        ("ДНЕЙ", f"{days}/{rule.min_paper_days}", days >= rule.min_paper_days),
    ]
    return [
        Criterion(
            criterion=name,
            display=f"{name} {text}" + (" ✓" if met else ""),
            is_met=met,
            tone="neutral" if met else "negative",
        )
        for name, text, met in items
    ]


def _period(name: str, trades: Sequence[ClosedTrade], start: date, capital: float) -> PeriodRow:
    chosen = [t for t in trades if _close_day(t) >= start]
    pnl = sum(t.pnl for t in chosen)
    return PeriodRow(
        period=name,
        pnl=money(pnl, signed=True),
        pnl_share=percent(pnl / capital, signed=True),
        trades=count(len(chosen)),
        win_rate=(
            percent(sum(t.pnl > 0 for t in chosen) / len(chosen)) if chosen else empty(NO_TRADES)
        ),
    )


def _pnl_since(trades: Sequence[ClosedTrade], start: date) -> float:
    return sum(t.pnl for t in trades if _close_day(t) >= start)


def _close_day(trade: ClosedTrade) -> date:
    return to_et(trade.closed_at).date()


def _mean(values: Sequence[float]) -> float | None:
    return statistics.fmean(values) if values else None


def _refresh_seconds(thresholds: Thresholds, now: datetime) -> int:
    settings = thresholds.dashboard
    if is_regular_session(now):
        return settings.refresh_session_seconds
    return settings.refresh_off_session_seconds
