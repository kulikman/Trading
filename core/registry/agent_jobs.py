"""Запуск агентов задачами события (T14): признаки агента — в feature_snapshot.

Задача события с полем `agent` (config/schedule.yaml) вызывает этого агента, если он загружен
реестром (включён, runs: event). Задача на стадии без признаков (T+1) вызывает шаг агента
`outcome` — итог отчёта. Выход агента — числовые поля его схемы; текст и пустые
значения в признаки не попадают. Признаки shadow-агентов тоже пишутся (решение их не видит, T13).
"""

import logging
from collections.abc import Mapping
from datetime import datetime
from functools import partial
from typing import Protocol, runtime_checkable

from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.config.schedule import ScheduleConfig
from core.db import models as orm
from core.db.store import save_feature_snapshot
from core.domain.earnings import FeatureSnapshot
from core.domain.schedule import EventJob
from core.domain.types import FeatureStage, ReportTime
from core.registry.protocols import Agent, EventContext
from core.scheduler.dispatch import Handler

logger = logging.getLogger(__name__)

STAGES: tuple[FeatureStage, ...] = ("T-14", "T-10", "T-7", "T-3", "T-1", "T0")
REPORT_TIMES: Mapping[str, ReportTime] = {"BMO": "BMO", "AMC": "AMC", "DURING": "DURING"}


@runtime_checkable
class OutcomeAgent(Protocol):
    """Агент с шагом после отчёта (стадии без признаков, например «Досье» на T+1)."""

    def outcome(self, session: Session, event_id: int, as_of: datetime) -> None:
        """Записать итог отчёта события."""


def features_of(output: BaseModel) -> dict[str, float]:
    """Числовые поля выхода агента (bool и None — не признаки)."""
    return {
        name: float(value)
        for name, value in output.model_dump().items()
        if isinstance(value, int | float) and not isinstance(value, bool)
    }


def run_agent(session: Session, agent: Agent, job: EventJob) -> FeatureSnapshot:
    """Один запуск агента по задаче события; признаки сохраняются один раз на версию агента."""
    event = session.get(orm.Event, job.event_id)
    if event is None:
        raise ValueError(f"event {job.event_id} not found")
    stage = _stage(job.stage)
    ctx = EventContext(
        event_id=event.id,
        ticker=event.ticker,
        report_date=event.report_date,
        report_time=REPORT_TIMES.get(event.report_time) if event.report_time else None,
        stage=stage,
        as_of=job.run_at,
        session=session,
    )
    snapshot = FeatureSnapshot(
        event_id=event.id,
        stage=stage,
        agent_id=agent.id,
        agent_version=agent.version,
        features=features_of(agent.run(ctx)),
    )
    if not save_feature_snapshot(session, snapshot):
        logger.info("features already stored", extra={"agent": agent.id, "event": event.id})
    return snapshot


def agent_handlers(schedule: ScheduleConfig, agents: Mapping[str, Agent]) -> dict[str, Handler]:
    """Обработчики диспетчера: имя задачи → запуск её агента (если агент загружен)."""
    handlers: dict[str, Handler] = {}
    for spec in schedule.event_jobs:
        if spec.agent is None or spec.agent not in agents:
            continue
        agent = agents[spec.agent]
        if spec.stage in STAGES:
            handlers[spec.job] = partial(_handle, agent)
        elif isinstance(agent, OutcomeAgent):
            handlers[spec.job] = partial(_handle_outcome, agent)
        else:  # ошибка конфигурации — при старте планировщика, а не в день отчёта
            raise ValueError(
                f"job {spec.job} at {spec.stage}: agent {spec.agent} has no outcome step"
            )
    return handlers


def _handle(agent: Agent, session: Session, job: EventJob) -> None:
    run_agent(session, agent, job)


def _handle_outcome(agent: OutcomeAgent, session: Session, job: EventJob) -> None:
    agent.outcome(session, job.event_id, job.run_at)


def _stage(value: str) -> FeatureStage:
    for stage in STAGES:
        if stage == value:
            return stage
    raise ValueError(f"no feature stage for job stage {value!r}")
