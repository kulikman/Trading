"""План задач события по SPEC §8: даты, перенос с выходных, время в UTC."""

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta

from core.config.schedule import EventJobSpec
from core.domain.schedule import EventJob
from core.domain.types import ReportTime
from core.session_guard import ET, is_regular_session, reaction_day, shift_to_trading_day


def job_key(event_id: int, stage: str, job: str) -> str:
    """Ключ идемпотентности задачи (event_id, stage, job) одной строкой — для логов."""
    return f"event:{event_id}:{stage}:{job}"


def plan_event_jobs(
    event_id: int,
    report_date: date,
    report_time: ReportTime | None,
    specs: Sequence[EventJobSpec],
) -> list[EventJob]:
    """Задачи события. Отсчёт — от дня реакции (AMC — следующий торговый день); неторговый день
    сдвигается по правилу задачи. Исполнение вне основной сессии помечается outside_session."""
    anchor = reaction_day(report_date, report_time)
    jobs: list[EventJob] = []
    for spec in specs:
        day = shift_to_trading_day(anchor + timedelta(days=spec.offset_days), spec.effective_shift)
        run_at = datetime.combine(day, spec.time_et, tzinfo=ET).astimezone(UTC)
        jobs.append(
            EventJob(
                event_id=event_id,
                stage=spec.stage,
                job=spec.job,
                kind=spec.kind,
                run_at=run_at,
                outside_session=spec.kind == "execution" and not is_regular_session(run_at),
            )
        )
    return sorted(jobs, key=lambda j: (j.run_at, j.stage, j.job))
