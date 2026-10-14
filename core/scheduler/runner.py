"""APScheduler 3.11 с хранилищем задач в Postgres (SPEC §3, §8).

Постоянных задач две: агент «Календарь» (торговые дни, 06:00 ET) и диспетчер задач событий.
Сами задачи событий — строки event_job (ключ event_id, stage, job), их берёт диспетчер.
"""

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.base import BaseScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from core.config.schedule import ScheduleConfig
from core.session_guard import ET

CALENDAR_JOB_ID = "calendar-daily"
DISPATCH_JOB_ID = "event-dispatch"
ARCHIVE_JOB_ID = "archive-daily"
CALENDAR_FUNC = "agents.calendar.job:run_calendar"
DISPATCH_FUNC = "core.scheduler.jobs:run_dispatch"
ARCHIVE_FUNC = "backtest.daily_archive:run_daily_archive"
JOBS_TABLE = "apscheduler_jobs"


def create_scheduler(database_url: str) -> BlockingScheduler:
    """Планировщик с задачами в Postgres (таблица создаётся миграцией 0004)."""
    return BlockingScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=database_url, tablename=JOBS_TABLE)},
        timezone="UTC",
    )


def register_jobs(scheduler: BaseScheduler, schedule: ScheduleConfig) -> None:
    """Повторная регистрация заменяет задачи, а не дублирует (replace_existing)."""
    run_time = schedule.calendar.run_time_et
    grace = schedule.scheduler.misfire_grace_seconds
    scheduler.add_job(
        CALENDAR_FUNC,
        CronTrigger(day_of_week="mon-fri", hour=run_time.hour, minute=run_time.minute, timezone=ET),
        id=CALENDAR_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=grace,
    )
    archive_time = schedule.archive.run_time_et
    scheduler.add_job(
        ARCHIVE_FUNC,
        CronTrigger(
            day_of_week="mon-fri", hour=archive_time.hour, minute=archive_time.minute, timezone=ET
        ),
        id=ARCHIVE_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=grace,
    )
    scheduler.add_job(
        DISPATCH_FUNC,
        IntervalTrigger(seconds=schedule.scheduler.dispatch_interval_seconds),
        id=DISPATCH_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=grace,
    )
