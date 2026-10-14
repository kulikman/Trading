"""Разбор отчёта в день T0 (T16, SPEC §10): факт EPS и выручки против консенсуса из Finnhub.

Задача `parse_report` (T0 07:30 ET) пишет факт и сюрприз в earnings_track; режим C читает их в
10:45 и, если отчёт к 07:30 ещё не дошёл до Finnhub, запрашивает его сам. Сюрприз — в процентах
(12.5 = +12,5%), как в архиве. Выручка и guidance условием входа не служат (решение заказчика
15.10.2026: записываются для сужения воронки по данным); guidance записывает «Досье» в T+1.
"""

import logging
from dataclasses import dataclass
from datetime import date
from functools import partial
from typing import Protocol

from sqlalchemy.orm import Session

from adapters.finnhub.models import FinnhubEarning
from core.db import models as orm
from core.db.store import save_report_facts
from core.domain.schedule import EventJob
from core.scheduler.dispatch import Handler

logger = logging.getLogger(__name__)


class ReportSource(Protocol):
    def earnings_calendar(
        self, start: date, end: date, symbol: str | None = None
    ) -> list[FinnhubEarning]:
        """Отчёты в окне дат."""


@dataclass(frozen=True)
class ReportFacts:
    eps_consensus: float | None
    eps_actual: float | None
    eps_surprise_pct: float | None
    rev_consensus: float | None
    rev_actual: float | None
    rev_surprise_pct: float | None

    def values(self) -> dict[str, float | None]:
        return {
            "eps_consensus": self.eps_consensus,
            "eps_actual": self.eps_actual,
            "eps_surprise_pct": self.eps_surprise_pct,
            "rev_consensus": self.rev_consensus,
            "rev_actual": self.rev_actual,
            "rev_surprise_pct": self.rev_surprise_pct,
        }


def surprise_pct(actual: float | None, estimate: float | None) -> float | None:
    """(факт − консенсус) / |консенсус| в процентах; консенсуса нет или он 0 — None."""
    if actual is None or estimate is None or estimate == 0:
        return None
    return (actual - estimate) / abs(estimate) * 100


def fetch_report_facts(source: ReportSource, ticker: str, report_date: date) -> ReportFacts | None:
    """Факт отчёта из календаря Finnhub; факта EPS ещё нет — None."""
    rows = [
        r
        for r in source.earnings_calendar(report_date, report_date, ticker)
        if r.date == report_date
    ]
    row = next((r for r in rows if r.symbol == ticker and r.eps_actual is not None), None)
    if row is None:
        return None
    return ReportFacts(
        eps_consensus=row.eps_estimate,
        eps_actual=row.eps_actual,
        eps_surprise_pct=surprise_pct(row.eps_actual, row.eps_estimate),
        rev_consensus=row.revenue_estimate,
        rev_actual=row.revenue_actual,
        rev_surprise_pct=surprise_pct(row.revenue_actual, row.revenue_estimate),
    )


def parse_report(session: Session, job: EventJob, *, source: ReportSource) -> ReportFacts | None:
    """Задача T0: факт отчёта события в earnings_track; факта ещё нет — режим C дозапросит."""
    event = session.get(orm.Event, job.event_id)
    if event is None:
        raise ValueError(f"event {job.event_id} not found")
    facts = fetch_report_facts(source, event.ticker, event.report_date)
    if facts is None:
        logger.warning(
            "report not yet in Finnhub",
            extra={"ticker": event.ticker, "report_date": event.report_date.isoformat()},
        )
        return None
    save_report_facts(session, event.ticker, event.report_date, event.report_time, facts.values())
    return facts


def report_handlers(source: ReportSource) -> dict[str, Handler]:
    """Обработчик задачи `parse_report` для диспетчера."""
    return {"parse_report": partial(_parse, source=source)}


def _parse(session: Session, job: EventJob, *, source: ReportSource) -> None:
    parse_report(session, job, source=source)
