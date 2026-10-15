"""Задачи планировщика: утренний (08:30 ET) и вечерний (16:30 ET) дайджест (SPEC §12, T18)."""

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from core.error_log import logged_job
from core.scheduler.jobs import engine
from core.session_guard import is_trading_day, to_et
from notify.digest import evening_text, morning_text
from notify.telegram.client import TelegramClient


@logged_job("digest-morning", lambda: engine())
def run_morning_digest(now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> bool:
    return _send(morning_text, now())


@logged_job("digest-evening", lambda: engine())
def run_evening_digest(now: Callable[[], datetime] = lambda: datetime.now(UTC)) -> bool:
    return _send(evening_text, now())


def _send(render: Callable[[Session, datetime], str], moment: datetime) -> bool:
    if not is_trading_day(to_et(moment).date()):
        return False
    client = TelegramClient.from_env()
    if client is None:
        return False
    with Session(engine()) as session:
        text = render(session, moment)
    client.send(text, silent=True)
    return True
