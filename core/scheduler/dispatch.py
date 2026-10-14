"""Диспетчер задач событий: берёт наступившие задачи из event_job и выполняет их (SPEC §8).

Опоздание больше grace (сервис простаивал) — задача missed и не выполняется задним числом:
вход в 15:30, сделанный в 17:00, хуже, чем никакого.
"""

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import models as orm
from core.domain.schedule import EventJob
from core.scheduler.plan import job_key

logger = logging.getLogger(__name__)

Handler = Callable[[Session, EventJob], None]

# Исполнители задач по имени job. Наполняются агентами и стратегиями (T13–T18).
HANDLERS: dict[str, Handler] = {}


@dataclass
class DispatchResult:
    done: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    missed: list[str] = field(default_factory=list)
    no_handler: list[str] = field(default_factory=list)


def dispatch_due(
    session: Session,
    *,
    now: datetime,
    grace: timedelta,
    handlers: Mapping[str, Handler],
) -> DispatchResult:
    """Выполнить все наступившие запланированные задачи. Параллельный диспетчер их не возьмёт."""
    rows = session.scalars(
        select(orm.EventJob)
        .where(orm.EventJob.status == "planned", orm.EventJob.run_at <= now)
        .order_by(orm.EventJob.run_at)
        .with_for_update(skip_locked=True)
    ).all()
    result = DispatchResult()
    for row in rows:
        key = job_key(row.event_id, row.stage, row.job)
        if row.run_at < now - grace:
            row.status = "missed"
            result.missed.append(key)
            logger.warning("event job missed", extra={"job": key, "run_at": row.run_at.isoformat()})
            continue
        handler = handlers.get(row.job)
        if handler is None:
            row.status = "no_handler"
            result.no_handler.append(key)
            logger.info("no handler for event job yet", extra={"job": key})
            continue
        try:
            with session.begin_nested():
                handler(session, EventJob.model_validate(row))
        except Exception:
            row.status = "failed"
            result.failed.append(key)
            logger.exception("event job failed", extra={"job": key})
            continue
        row.status = "done"
        result.done.append(key)
    return result
