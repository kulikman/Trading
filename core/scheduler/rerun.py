"""`make rerun-job ARGS="NFLX T-7 options"`: повторить упавшую задачу события.

Задача выполняется с тем же моментом оценки, что в расписании (run_at), — признаки как при
плановом запуске. Успех ставит ошибкам этой задачи «решено» (журнал «Настройки → Логи»).
"""

import argparse
import logging
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import models as orm
from core.scheduler.dispatch import Handler, run_job
from core.scheduler.jobs import engine, handlers

logger = logging.getLogger("core.scheduler.rerun")

RERUNNABLE = ("failed", "missed")


def rerun(
    session: Session,
    ticker: str,
    stage: str,
    job: str,
    *,
    job_handlers: Mapping[str, Handler],
    now: datetime,
) -> bool:
    """Повторить последнюю упавшую или пропущенную задачу (тикер, стадия, задача)."""
    row = session.scalars(
        select(orm.EventJob)
        .join(orm.Event, orm.Event.id == orm.EventJob.event_id)
        .where(
            orm.Event.ticker == ticker,
            orm.EventJob.stage == stage,
            orm.EventJob.job == job,
            orm.EventJob.status.in_(RERUNNABLE),
        )
        .order_by(orm.EventJob.run_at.desc())
        .limit(1)
    ).first()
    if row is None:
        raise LookupError(f"{ticker} {stage} {job}: no failed or missed job to rerun")
    handler = job_handlers.get(job)
    if handler is None:
        raise LookupError(f"{job}: no handler (agent not loaded)")
    return run_job(session, row, handler, now=now)


def main(
    argv: Sequence[str] | None = None,
    job_handlers: Callable[[], dict[str, Handler]] = handlers,
) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    parser = argparse.ArgumentParser(description="Повторить упавшую задачу события")
    parser.add_argument("ticker")
    parser.add_argument("stage", help="стадия, например T-7")
    parser.add_argument("job", help="задача, например options")
    args = parser.parse_args(argv)
    with Session(engine()) as session, session.begin():
        is_done = rerun(
            session,
            args.ticker.upper(),
            args.stage,
            args.job,
            job_handlers=job_handlers(),
            now=datetime.now(UTC),
        )
    logger.info(
        "Задача %s: %s",
        " ".join([args.ticker.upper(), args.stage, args.job]),
        "выполнена, ошибка решена" if is_done else "снова упала — см. «Настройки → Логи»",
    )
    return 0 if is_done else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
