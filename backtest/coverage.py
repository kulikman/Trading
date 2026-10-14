"""Покрытие архива прошлых отчётов (T11): сколько отчётов и сколько с полным набором полей."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backtest.archive_steps import DateCheck
from core.db import models as orm

FULL_FIELDS = (
    "eps_consensus",
    "eps_actual",
    "rev_actual",
    "implied_move",
    "actual_move",
    "move_ratio",
)


@dataclass(frozen=True)
class Coverage:
    ticker: str
    reports: int
    eps: int
    revenue: int
    implied: int
    actual: int
    full: int


def coverage(session: Session, since: date, until: date) -> list[Coverage]:
    """По компаниям: отчёты в окне [since, until) и сколько из них с каждым полем."""
    track = orm.EarningsTrack
    rows = session.execute(
        select(
            track.ticker,
            func.count(),
            func.count().filter(track.eps_actual.is_not(None), track.eps_consensus.is_not(None)),
            func.count().filter(track.rev_actual.is_not(None)),
            func.count().filter(track.implied_move.is_not(None)),
            func.count().filter(track.actual_move.is_not(None)),
            func.count().filter(*[getattr(track, c).is_not(None) for c in FULL_FIELDS]),
        )
        .where(track.report_date >= since, track.report_date < until)
        .group_by(track.ticker)
        .order_by(track.ticker)
    ).all()
    return [Coverage(*row) for row in rows]


def render(
    rows: Sequence[Coverage],
    checks: Sequence[DateCheck],
    *,
    since: date,
    until: date,
    pending: Sequence[str],
) -> str:
    """Markdown-отчёт: итоги, таблица по компаниям, расхождения дат с 8-K."""
    total = Coverage(
        "Всего",
        *(
            sum(getattr(r, f) for r in rows)
            for f in ("reports", "eps", "revenue", "implied", "actual", "full")
        ),
    )
    lines = [
        f"# Покрытие архива отчётов — {until:%d.%m.%Y}",
        "",
        f"Окно: отчёты с {since:%d.%m.%Y} по {until:%d.%m.%Y} (доступ к ценам опционов — 2 года).",
        (
            "Полный набор: консенсус и факт EPS, выручка-факт, implied move, фактическое движение,"
            " move_ratio."
        ),
        "Консенсуса выручки за прошлое в бесплатных источниках нет — в полный набор не входит.",
        "",
        f"Компаний в архиве: {len(rows)}."
        + (f" Ещё не загружены (лимит Alpha Vantage): {', '.join(pending)}." if pending else ""),
        "",
        "| Компания | Отчётов | EPS | Выручка | Implied move | Движение | Полный набор |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in [*rows, total]:
        name = f"**{row.ticker}**" if row is total else row.ticker
        lines.append(
            f"| {name} | {row.reports} | {row.eps} | {row.revenue} | {row.implied} | "
            f"{row.actual} | {row.full} ({_share(row.full, row.reports)}) |"
        )
    problems = [c for c in checks if c.status != "ok"]
    ok = len(checks) - len(problems)
    lines += [
        "",
        "## Сверка даты отчёта с 8-K (SEC, п. 2.02)",
        "",
        (
            f"Проверено {len(checks)}: совпадает (0–1 день) — {ok}, "
            f"расхождение — {sum(c.status == 'mismatch' for c in checks)}, "
            f"нет 8-K рядом — {sum(c.status == 'no_8k' for c in checks)}."
        ),
    ]
    if problems:
        lines += ["", "| Компания | Дата отчёта | 8-K | Сдвиг, дн. |", "|---|---|---|---:|"]
        for check in problems:
            filed = f"{check.filing_date:%d.%m.%Y}" if check.filing_date else "нет"
            shift = "" if check.shift_days is None else str(check.shift_days)
            lines.append(f"| {check.ticker} | {check.report_date:%d.%m.%Y} | {filed} | {shift} |")
    return "\n".join(lines) + "\n"


def _share(part: int, whole: int) -> str:
    return f"{part / whole:.0%}" if whole else "—"
