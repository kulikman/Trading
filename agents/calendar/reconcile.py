"""Сверка даты отчёта по двум источникам (SPEC §6): Finnhub — основной, Alpha Vantage — второй."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from adapters.alphavantage.models import AvCalendarRow
from adapters.finnhub.models import FinnhubEarning
from core.domain.types import DateStatus, ReportTime


@dataclass(frozen=True)
class Observation:
    ticker: str
    report_date: date
    report_time: ReportTime | None
    fiscal_period: str | None
    date_status: DateStatus
    sources: list[dict[str, Any]]
    mismatch: str | None  # текст расхождения дат или None


def reconcile(
    item: FinnhubEarning, av_rows: Sequence[AvCalendarRow], window_days: int
) -> Observation:
    """confirmed — даты совпали; projected — один источник или расхождение (mismatch)."""
    candidates = [r for r in av_rows if abs((r.report_date - item.date).days) <= window_days]
    av = (
        min(candidates, key=lambda r: abs((r.report_date - item.date).days)) if candidates else None
    )
    sources: list[dict[str, Any]] = [
        {"source": "finnhub", "date": item.date.isoformat(), "time": item.hour or None}
    ]
    if av is not None:
        sources.append(
            {
                "source": "alphavantage",
                "date": av.report_date.isoformat(),
                "time": av.time_of_the_day,
            }
        )
    mismatch = None
    if av is not None and av.report_date != item.date:
        mismatch = f"finnhub {item.date.isoformat()} vs alphavantage {av.report_date.isoformat()}"
    confirmed = av is not None and mismatch is None
    return Observation(
        ticker=item.symbol,
        report_date=item.date,
        report_time=item.report_time or (av.report_time if av is not None else None),
        fiscal_period=item.fiscal_period,
        date_status="confirmed" if confirmed else "projected",
        sources=sources,
        mismatch=mismatch,
    )
