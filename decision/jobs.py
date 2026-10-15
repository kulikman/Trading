"""Задачи решения в расписании (T16): какие стратегии решают на какой задаче и итог после T0.

Задача с полем `strategies` (config/schedule.yaml) запускает Chief Trader по этим стратегиям.
`mode_c_decision` (T0 10:45) после своих стратегий подводит итог события; `outcome` (T+1)
подводит его ещё раз — у каждого события после T0 есть Decision, даже если задачи T0 не прошли.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from functools import partial

from sqlalchemy.orm import Session

from core.config import AppConfig
from core.domain.schedule import EventJob
from core.registry.protocols import Strategy
from core.scheduler.dispatch import Handler
from decision.chief import finalize, run_decision

FINALIZE_JOBS = ("mode_c_decision", "outcome")


def decision_handlers(config: AppConfig, strategies: Mapping[str, Strategy]) -> dict[str, Handler]:
    """Обработчики диспетчера: задачи со стратегиями и задачи итога события."""
    handlers: dict[str, Handler] = {}
    for spec in config.schedule.event_jobs:
        if spec.strategies:
            handlers[spec.job] = partial(
                _decide,
                strategy_ids=tuple(spec.strategies),
                strategies=strategies,
                config=config,
                is_final=spec.job in FINALIZE_JOBS,
            )
    for job in FINALIZE_JOBS:
        handlers.setdefault(job, _finalize)
    return handlers


def _decide(
    session: Session,
    job: EventJob,
    *,
    strategy_ids: Sequence[str],
    strategies: Mapping[str, Strategy],
    config: AppConfig,
    is_final: bool,
) -> None:
    run_decision(session, job, strategy_ids, strategies, config=config, now=_now())
    if is_final:
        finalize(session, job.event_id, _now())


def _finalize(session: Session, job: EventJob) -> None:
    finalize(session, job.event_id, _now())


def _now() -> datetime:
    return datetime.now(UTC)
