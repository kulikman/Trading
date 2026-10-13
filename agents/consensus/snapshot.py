"""Ежедневный снимок консенсуса в consensus_snapshot (SPEC §5, §8; TASKS T06).

Свой архив пересмотров: бесплатные источники отдают только текущую оценку.
"""

from collections.abc import Collection
from datetime import date, timedelta
from typing import Protocol

from sqlalchemy.orm import Session

from adapters.finnhub.mapping import consensus_snapshots
from adapters.finnhub.models import FinnhubEarning
from core.db.store import save_consensus_snapshots


class EarningsCalendarSource(Protocol):
    def earnings_calendar(
        self, start: date, end: date, symbol: str | None = None
    ) -> list[FinnhubEarning]:
        """Отчёты в окне дат."""


def take_consensus_snapshot(
    source: EarningsCalendarSource,
    session: Session,
    *,
    as_of: date,
    lookahead_days: int,
    tickers: Collection[str],
) -> int:
    """Снимок консенсуса предстоящих отчётов вселенной на дату as_of. Возвращает число строк."""
    items = source.earnings_calendar(as_of, as_of + timedelta(days=lookahead_days))
    return save_consensus_snapshots(session, consensus_snapshots(items, as_of, tickers))
