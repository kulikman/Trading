"""Расписание события и журнал его изменений (SPEC §8, DASHBOARD.md §4.1)."""

from pydantic import AwareDatetime

from core.domain.base import DomainModel
from core.domain.types import EventJobStatus, JobKind


class EventJob(DomainModel):
    event_id: int
    stage: str
    job: str
    kind: JobKind
    run_at: AwareDatetime
    status: EventJobStatus = "planned"
    outside_session: bool = False


class EventChange(DomainModel):
    id: int | None = None
    event_id: int
    at: AwareDatetime
    field: str
    old_value: str | None = None
    new_value: str | None = None
    reason: str | None = None
