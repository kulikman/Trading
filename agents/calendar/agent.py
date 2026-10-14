"""Агент «Календарь» (SPEC §8): ежедневно 06:00 ET — события отчётов вселенной на T−21.

Дата подтверждена (confirmed) только при совпадении Finnhub и Alpha Vantage (SPEC §6).
Расхождение — DATA_CALENDAR: запись в журнал события, лог и сообщение «СИСТЕМА».
Перенос даты не создаёт новое событие: старое обновляется, изменение пишется в журнал.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.alphavantage.models import AvCalendarRow
from adapters.errors import DataError
from adapters.finnhub.models import FinnhubEarning
from agents.calendar.reconcile import Observation, reconcile
from core.config.schedule import ScheduleConfig
from core.config.universe import Universe
from core.db import models as orm
from core.db.store import save_event_jobs, sync_universe
from core.domain.earnings import Event
from core.scheduler.plan import plan_event_jobs
from notify.system import SystemNotifier

logger = logging.getLogger(__name__)

DATA_CALENDAR = "DATA_CALENDAR"
TRACKED_FIELDS = ("report_date", "report_time", "date_status", "fiscal_period")


class FinnhubCalendar(Protocol):
    def earnings_calendar(
        self, start: date, end: date, symbol: str | None = None
    ) -> list[FinnhubEarning]:
        """Отчёты в окне дат."""


class AlphaVantageCalendar(Protocol):
    def earnings_calendar(self, symbol: str | None = None) -> list[AvCalendarRow]:
        """Предстоящие отчёты рынка."""


@dataclass
class CalendarRunResult:
    created: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    mismatches: list[str] = field(default_factory=list)
    jobs_planned: int = 0


class CalendarAgent:
    id = "calendar"
    version = "0.1.0"

    def __init__(
        self,
        *,
        finnhub: FinnhubCalendar,
        alphavantage: AlphaVantageCalendar,
        notifier: SystemNotifier,
        universe: Universe,
        schedule: ScheduleConfig,
    ) -> None:
        self._finnhub = finnhub
        self._alphavantage = alphavantage
        self._notifier = notifier
        self._universe = universe
        self._schedule = schedule

    def run(self, session: Session, *, as_of: date, now: datetime) -> CalendarRunResult:
        """Один прогон: синхронизация вселенной, события, план задач. Повтор — без дублей."""
        settings = self._schedule.calendar
        sync_universe(session, self._universe)
        tickers = set(self._universe.tickers())
        try:
            items = self._finnhub.earnings_calendar(
                as_of, as_of + timedelta(days=settings.lookahead_days)
            )
        except DataError as exc:
            self._notifier.system(f"Календарь: Finnhub недоступен ({exc})", code=DATA_CALENDAR)
            raise
        av_by_ticker = self._alphavantage_rows(tickers)
        result = CalendarRunResult()
        for item in items:
            if item.symbol not in tickers:
                continue
            observation = reconcile(
                item, av_by_ticker.get(item.symbol, []), settings.date_match_window_days
            )
            event = self._upsert_event(session, observation, now, result)
            jobs = plan_event_jobs(
                event.id, event.report_date, observation.report_time, self._schedule.event_jobs
            )
            result.jobs_planned += save_event_jobs(session, jobs)
        logger.info(
            "calendar run",
            extra={
                "events_created": len(result.created),
                "events_updated": len(result.updated),
                "date_mismatches": len(result.mismatches),
                "jobs_planned": result.jobs_planned,
            },
        )
        return result

    def _alphavantage_rows(self, tickers: set[str]) -> dict[str, list[AvCalendarRow]]:
        try:
            rows = self._alphavantage.earnings_calendar()
        except DataError as exc:
            self._notifier.system(
                f"Календарь: Alpha Vantage недоступен — даты не подтверждаются ({exc})",
                code=DATA_CALENDAR,
            )
            return {}
        by_ticker: dict[str, list[AvCalendarRow]] = {}
        for row in rows:
            if row.symbol in tickers:
                by_ticker.setdefault(row.symbol, []).append(row)
        return by_ticker

    def _upsert_event(
        self, session: Session, obs: Observation, now: datetime, result: CalendarRunResult
    ) -> orm.Event:
        Event(  # проверка правил домена (confirmed — минимум два источника) до записи
            ticker=obs.ticker,
            report_date=obs.report_date,
            report_time=obs.report_time,
            fiscal_period=obs.fiscal_period,
            date_status=obs.date_status,
            date_sources=obs.sources,
        )
        existing = self._find_existing(session, obs)
        if existing is None:
            event = orm.Event(
                ticker=obs.ticker,
                report_date=obs.report_date,
                report_time=obs.report_time,
                fiscal_period=obs.fiscal_period,
                date_status=obs.date_status,
                date_sources=obs.sources,
                queue_status="planned",
            )
            session.add(event)
            session.flush()
            result.created.append(obs.ticker)
            if obs.mismatch:
                self._record_mismatch(session, event, obs, now, result)
            return event
        previous_mismatch = _mismatch_key(existing.date_sources)
        changed = False
        for name in TRACKED_FIELDS:
            new = getattr(obs, name)
            old = getattr(existing, name)
            if new == old or (name == "fiscal_period" and new is None):
                continue
            session.add(
                orm.EventChange(
                    event_id=existing.id,
                    at=now,
                    field=name,
                    old_value=None if old is None else str(old),
                    new_value=None if new is None else str(new),
                    reason="calendar: finnhub",
                )
            )
            setattr(existing, name, new)
            changed = True
        existing.date_sources = obs.sources
        if changed:
            result.updated.append(obs.ticker)
        if obs.mismatch and _mismatch_key(obs.sources) != previous_mismatch:
            self._record_mismatch(session, existing, obs, now, result)
        session.flush()
        return existing

    def _find_existing(self, session: Session, obs: Observation) -> orm.Event | None:
        """То же событие: тот же фискальный квартал, иначе ближайшая дата в окне переноса."""
        rows = session.scalars(
            select(orm.Event).where(
                orm.Event.ticker == obs.ticker, orm.Event.queue_status != "done"
            )
        ).all()
        if obs.fiscal_period is not None:
            for row in rows:
                if row.fiscal_period == obs.fiscal_period:
                    return row
        window = self._schedule.calendar.same_event_window_days
        near = [r for r in rows if abs((r.report_date - obs.report_date).days) <= window]
        return (
            min(near, key=lambda r: abs((r.report_date - obs.report_date).days)) if near else None
        )

    def _record_mismatch(
        self,
        session: Session,
        event: orm.Event,
        obs: Observation,
        now: datetime,
        result: CalendarRunResult,
    ) -> None:
        reason = f"{DATA_CALENDAR}: {obs.mismatch}"
        session.add(
            orm.EventChange(
                event_id=event.id,
                at=now,
                field="date_check",
                old_value=None,
                new_value="mismatch",
                reason=reason,
            )
        )
        result.mismatches.append(obs.ticker)
        logger.warning("report date mismatch", extra={"ticker": obs.ticker, "reason": reason})
        self._notifier.system(
            f"{obs.ticker}: расхождение даты отчёта — {obs.mismatch}", code=DATA_CALENDAR
        )


def _mismatch_key(sources: object) -> tuple[str, ...] | None:
    """Пара дат источников, если они расходятся, — чтобы не сообщать об одном расхождении дважды."""
    if not isinstance(sources, list):
        return None
    dates = tuple(str(s.get("date")) for s in sources if isinstance(s, dict))
    return dates if len(set(dates)) > 1 else None
