"""APScheduler 3.11 с хранилищем задач в Postgres (SPEC §3, §8).

Постоянные задачи: агент «Календарь» (06:00 ET), уровень Black Swan (06:05 ET),
снимок консенсуса (06:10 ET), капитализация компаний (07:30 ET), новости (07:45 ET),
трейлинг-стоп (16:20 ET), дайджесты (08:30 и 16:30 ET), архив (18:30 ET),
эмуляция входа paper (каждые несколько минут 10:46–16:30 ET), watchlist (воскресенье 18:00 ET)
и диспетчер задач событий.
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
CONSENSUS_JOB_ID = "consensus-daily"
TRAILING_JOB_ID = "trailing-daily"
MORNING_DIGEST_JOB_ID = "digest-morning"
EVENING_DIGEST_JOB_ID = "digest-evening"
WEEKLY_DIGEST_JOB_ID = "digest-weekly"
NEWS_JOB_ID = "news-daily"
MARKET_JOB_ID = "market-daily"
CALENDAR_FUNC = "agents.calendar.job:run_calendar"
DISPATCH_FUNC = "core.scheduler.jobs:run_dispatch"
ARCHIVE_FUNC = "backtest.daily_archive:run_daily_archive"
CONSENSUS_FUNC = "agents.consensus.job:run_consensus_snapshot"
TRAILING_FUNC = "execution.trailing:run_trailing_update"
MORNING_DIGEST_FUNC = "notify.digest_jobs:run_morning_digest"
EVENING_DIGEST_FUNC = "notify.digest_jobs:run_evening_digest"
WEEKLY_DIGEST_FUNC = "notify.digest_jobs:run_weekly_calendar"
NEWS_FUNC = "agents.news.job:run_news"
MARKET_FUNC = "agents.macro.daily:run_market_level"
WATCHLIST_JOB_ID = "watchlist-refresh"
WATCHLIST_FUNC = "agents.watchlist.job:run_watchlist_refresh"
MARKET_CAP_JOB_ID = "market-cap-daily"
MARKET_CAP_FUNC = "agents.macro.market_cap:run_market_cap_refresh"
PAPER_FILL_JOB_ID = "paper-fill"
PAPER_FILL_FUNC = "execution.paper_fill:run_paper_fill"
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
    for func, job_id, at in (
        (ARCHIVE_FUNC, ARCHIVE_JOB_ID, schedule.archive.run_time_et),
        (CONSENSUS_FUNC, CONSENSUS_JOB_ID, schedule.consensus.run_time_et),
        (TRAILING_FUNC, TRAILING_JOB_ID, schedule.trailing.run_time_et),
        (MORNING_DIGEST_FUNC, MORNING_DIGEST_JOB_ID, schedule.digest.morning_et),
        (EVENING_DIGEST_FUNC, EVENING_DIGEST_JOB_ID, schedule.digest.evening_et),
        (NEWS_FUNC, NEWS_JOB_ID, schedule.news.run_time_et),
        (MARKET_FUNC, MARKET_JOB_ID, schedule.market.run_time_et),
    ):
        scheduler.add_job(
            func,
            CronTrigger(day_of_week="mon-fri", hour=at.hour, minute=at.minute, timezone=ET),
            id=job_id,
            replace_existing=True,
            coalesce=True,
            max_instances=1,
            misfire_grace_time=grace,
        )
    weekly = schedule.digest.weekly_monday_utc
    scheduler.add_job(
        WEEKLY_DIGEST_FUNC,
        CronTrigger(day_of_week="mon", hour=weekly.hour, minute=weekly.minute),
        id=WEEKLY_DIGEST_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=grace,
    )
    scheduler.add_job(
        WATCHLIST_FUNC,
        CronTrigger(day_of_week="sun", hour=18, minute=0, timezone=ET),
        id=WATCHLIST_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=grace,
    )
    scheduler.add_job(
        MARKET_CAP_FUNC,
        CronTrigger(day_of_week="mon-fri", hour=7, minute=30, timezone=ET),
        id=MARKET_CAP_JOB_ID,
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=grace,
    )
    fill = schedule.paper_fill
    scheduler.add_job(
        PAPER_FILL_FUNC,
        CronTrigger(
            day_of_week="mon-fri",
            hour=f"{fill.from_et.hour}-{fill.until_et.hour}",
            minute=f"*/{fill.every_minutes}",
            timezone=ET,
        ),
        id=PAPER_FILL_JOB_ID,
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
