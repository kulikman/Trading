"""Расписание события и журнал его изменений (SPEC §8, DASHBOARD.md §4.1)."""

from pydantic import AwareDatetime

from core.domain.base import DomainModel
from core.domain.types import ErrorLevel, EventJobStatus, JobKind


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


class ErrorLogEntry(DomainModel):
    """Ошибка задачи в журнале (экран «Настройки → Логи ошибок»); текст — без секретов."""

    id: int | None = None
    at: AwareDatetime
    level: ErrorLevel = "error"
    source: str
    event_id: int | None = None
    ticker: str | None = None
    stage: str | None = None
    error_type: str
    message: str
    resolved_at: AwareDatetime | None = None
