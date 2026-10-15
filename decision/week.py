"""Отбор недели (SPEC §17 п.2, E2d): одна функция для экрана «Неделя» и понедельничного дайджеста.

События ближайших 5 торговых дней сортируются по ожидаемой прибыли с учётом размера (не по
уверенности; решение заказчика 15.10.2026): риск сделки, $ × (p·b − (1−p)) — та же формула, что у
Келли; p — вероятность модели в последнем прошедшем шаге решения стратегии, b — средний выигрыш /
средний проигрыш закрытых сделок конструкции (правило 30, иначе стартовое b). У события берётся
лучшая стратегия. Топ — 5 событий с наибольшей ожидаемой прибылью; остальные — по дате, со статусом
и кодами пропуска. Режим без модели (C) и события, по которым решения ещё не было, в топ не
попадают: ожидаемой прибыли у них нет («по сигналу T0» / «решение впереди»).
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config.thresholds import Thresholds
from core.db import models as orm
from core.session_guard import is_trading_day
from decision.capital import win_loss_ratio

WINDOW_TRADING_DAYS = 5
TOP_SIZE = 5


@dataclass(frozen=True)
class WeekPick:
    """Событие недели и лучшая по ожидаемой прибыли стратегия (если решение уже было)."""

    event: orm.Event
    decision: orm.Decision | None = None
    mode: str | None = None
    construction: str | None = None
    confidence: float | None = None
    risk_usd: float | None = None
    expected_usd: float | None = None
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WeekSelection:
    first: date
    last: date
    top: list[WeekPick]
    rest: list[WeekPick]


def week_window(today: date) -> tuple[date, date]:
    """Первый и последний из ближайших 5 торговых дней, считая сегодня (если торговый)."""
    days: list[date] = []
    current = today
    while len(days) < WINDOW_TRADING_DAYS:
        if is_trading_day(current):
            days.append(current)
        current += timedelta(days=1)
    return days[0], days[-1]


def select_week(session: Session, today: date, thresholds: Thresholds) -> WeekSelection:
    """Топ по ожидаемой прибыли и остальные события окна по дате."""
    first, last = week_window(today)
    events = session.scalars(
        select(orm.Event)
        .where(orm.Event.report_date >= first, orm.Event.report_date <= last)
        .order_by(orm.Event.report_date, orm.Event.ticker)
    ).all()
    capital = thresholds.capital.module_usd
    ratios: dict[str, float] = {}
    picks = [_pick(session, event, capital, thresholds, ratios) for event in events]
    ranked = sorted(
        (p for p in picks if p.expected_usd is not None),
        key=lambda p: (-(p.expected_usd or 0.0), p.event.report_date, p.event.ticker),
    )
    top = ranked[:TOP_SIZE]
    chosen = {p.event.id for p in top}
    return WeekSelection(first, last, top, [p for p in picks if p.event.id not in chosen])


def _pick(
    session: Session,
    event: orm.Event,
    capital: float,
    thresholds: Thresholds,
    ratios: dict[str, float],
) -> WeekPick:
    decisions = session.scalars(
        select(orm.Decision).where(orm.Decision.event_id == event.id).order_by(orm.Decision.id)
    ).all()
    entered = next((d for d in decisions if d.status == "ENTERED"), None)
    decision = entered or next(iter(decisions), None)
    steps = session.scalars(
        select(orm.DecisionStep)
        .where(
            orm.DecisionStep.event_id == event.id,
            orm.DecisionStep.outcome == "proposal",
            orm.DecisionStep.is_shadow.is_(False),
        )
        .order_by(orm.DecisionStep.id.desc())
    ).all()
    latest: dict[str, orm.DecisionStep] = {}
    for step in steps:  # последний шаг каждой стратегии
        latest.setdefault(step.strategy_id, step)
    best: WeekPick | None = None
    for step in latest.values():
        expected = _expected(step, capital, thresholds, session, ratios)
        if expected is None or (best is not None and expected <= (best.expected_usd or 0.0)):
            continue
        best = WeekPick(
            event=event,
            decision=decision,
            mode=step.mode,
            construction=step.construction,
            confidence=step.confidence,
            risk_usd=capital * (step.risk_fraction or 0.0),
            expected_usd=expected,
        )
    if best is not None:
        return best
    reasons = list(decision.reasons) if decision is not None and decision.reasons else []
    return WeekPick(event=event, decision=decision, reasons=reasons)


def _expected(
    step: orm.DecisionStep,
    capital: float,
    thresholds: Thresholds,
    session: Session,
    ratios: dict[str, float],
) -> float | None:
    """Риск $ × (p·b − (1−p)); нет вероятности модели или риска — None."""
    p, risk = step.probability, capital * (step.risk_fraction or 0.0)
    if not p or risk <= 0 or step.construction is None:
        return None
    if step.construction not in ratios:
        ratios[step.construction] = win_loss_ratio(session, step.construction, thresholds)
    b = ratios[step.construction]
    return risk * (p * b - (1 - p))
