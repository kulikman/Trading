"""Шаги сборки архива прошлых отчётов (T11): выручка-факт, фактическое движение, сверка дат.

Определения (решение заказчика 14.10.2026):
- actual_move — закрытие в день реакции / закрытие накануне − 1, со знаком; то же «накануне», от
  которого считается implied_move (T10);
- move_ratio — |actual_move| / implied_move.
Прибыль сделок бэктест (T12) считает отдельно, по внутридневным ценам выхода до 11:00 ET.
"""

import logging
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from adapters.edgar.models import Filing
from adapters.massive.history import EventDays
from core.db.store import set_date_check, update_earnings
from core.domain.earnings import EarningsTrack
from core.domain.financials import FinancialQuarter
from core.domain.types import DateCheckStatus
from core.session_guard import to_et

logger = logging.getLogger(__name__)

REVENUE_METRIC = "revenue"


@dataclass(frozen=True)
class DateCheck:
    ticker: str
    report_date: date
    filing_date: date | None
    status: DateCheckStatus

    @property
    def shift_days(self) -> int | None:
        return None if self.filing_date is None else (self.filing_date - self.report_date).days


@dataclass
class ArchiveStats:
    revenue_matched: int = 0
    moves: int = 0
    ratios: int = 0
    missing_prices: int = 0


def match_period(fiscal_end: date, periods: Iterable[date], tolerance_days: int) -> date | None:
    """Квартал XBRL для конца квартала из Alpha Vantage: ближайший в пределах допуска.

    Alpha Vantage даёт конец месяца, XBRL — фактическую дату (у 52/53-недельного года она
    может отличаться на несколько дней).
    """
    near = [p for p in periods if abs((p - fiscal_end).days) <= tolerance_days]
    return min(near, key=lambda p: (abs((p - fiscal_end).days), p)) if near else None


def apply_revenue(
    session: Session,
    ticker: str,
    rows: Sequence[EarningsTrack],
    quarters: Sequence[FinancialQuarter],
    tolerance_days: int,
) -> int:
    """rev_actual отчётов из квартальной выручки SEC. Возвращает число сопоставленных отчётов."""
    revenue = {q.period_end: q.value for q in quarters if q.metric == REVENUE_METRIC}
    matched = 0
    for row in rows:
        if row.fiscal_period_end is None:
            continue
        period = match_period(row.fiscal_period_end, revenue, tolerance_days)
        if period is None:
            continue
        update_earnings(session, ticker, row.report_date, {"rev_actual": revenue[period]})
        matched += 1
    return matched


def apply_moves(
    session: Session,
    ticker: str,
    rows: Sequence[EarningsTrack],
    closes: Mapping[date, float],
    today: date,
    stats: ArchiveStats,
) -> None:
    """actual_move и move_ratio прошедших отчётов. Нет цены закрытия — поле остаётся пустым."""
    for row in rows:
        days = EventDays.of(row.report_date, row.report_time)
        if days.reaction >= today:
            continue  # реакция ещё не закрылась
        before, after = closes.get(days.pre), closes.get(days.reaction)
        if before is None or after is None or before <= 0:
            stats.missing_prices += 1
            logger.warning(
                "no stock close for actual move",
                extra={"ticker": ticker, "report_date": row.report_date.isoformat()},
            )
            continue
        move = after / before - 1
        ratio = abs(move) / row.implied_move if row.implied_move else None
        update_earnings(
            session, ticker, row.report_date, {"actual_move": move, "move_ratio": ratio}
        )
        stats.moves += 1
        stats.ratios += ratio is not None


def check_dates(
    ticker: str,
    reports: Sequence[EarningsTrack],
    filings: Sequence[Filing],
    search_days: int,
) -> list[DateCheck]:
    """Дата отчёта (Alpha Vantage) против подачи 8-K о результатах (SEC).

    Дата подачи — по ET из времени приёма (AMC-отчёт, поданный вечером, — тот же день).
    Ближайший 8-K в пределах search_days: разница 0 или 1 день — ok, иначе — mismatch
    (дата источника под сомнением: у C Alpha Vantage дал дату 10-Q вместо пресс-релиза);
    нет — no_8k.
    """
    filed = sorted({_filing_day(f) for f in filings})
    checks = []
    for report in reports:
        near = [d for d in filed if abs((d - report.report_date).days) <= search_days]
        if not near:
            checks.append(DateCheck(ticker, report.report_date, None, "no_8k"))
            continue
        closest = min(near, key=lambda d: (abs((d - report.report_date).days), d))
        shift = (closest - report.report_date).days
        status: DateCheckStatus = "ok" if shift in (0, 1) else "mismatch"
        checks.append(DateCheck(ticker, report.report_date, closest, status))
        if status == "mismatch":
            logger.warning(
                "report date differs from 8-K",
                extra={"ticker": ticker, "report_date": report.report_date.isoformat()},
            )
    return checks


def save_date_checks(session: Session, checks: Sequence[DateCheck]) -> None:
    """Результаты сверки — в earnings_track."""
    for check in checks:
        set_date_check(session, check.ticker, check.report_date, check.filing_date, check.status)


def _filing_day(filing: Filing) -> date:
    return to_et(filing.accepted_at).date() if filing.accepted_at else filing.filing_date
