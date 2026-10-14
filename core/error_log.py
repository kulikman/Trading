"""Журнал задач (экран «Настройки → Логи»): что упало, когда и почему, и когда снова заработало.

Ошибка решена, когда та же задача потом отработала (у задачи события — тот же тикер и стадия):
ошибке ставится resolved_at, в журнал пишется одна запись «ok».

Текст ошибки сохраняется без секретов: значения переменных окружения с KEY / TOKEN / SECRET /
PASSWORD в имени и параметры ключей в адресах (`apikey=…`, `token=…`) заменяются на «***».
"""

import functools
import logging
import os
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from core.db import models as orm

logger = logging.getLogger(__name__)

SECRET_ENV_NAME = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)$", re.IGNORECASE)
SECRET_QUERY = re.compile(r"((?:api_?key|token|apikey)=)[^&\s\"']+", re.IGNORECASE)
MIN_SECRET_LENGTH = 8
MAX_MESSAGE_LENGTH = 2000
MASK = "***"


def redact(text: str, env: Mapping[str, str] | None = None) -> str:
    """Убрать секреты из текста ошибки."""
    values = os.environ if env is None else env
    for name, value in values.items():
        if SECRET_ENV_NAME.search(name) and len(value) >= MIN_SECRET_LENGTH:
            text = text.replace(value, MASK)
    return SECRET_QUERY.sub(rf"\g<1>{MASK}", text)


def error_entry(
    source: str,
    error: BaseException,
    *,
    at: datetime,
    event_id: int | None = None,
    ticker: str | None = None,
    stage: str | None = None,
) -> orm.ErrorLog:
    """Строка журнала: тип и текст ошибки без секретов, не длиннее MAX_MESSAGE_LENGTH."""
    message = redact(str(error) or type(error).__name__)
    return orm.ErrorLog(
        at=at,
        source=source,
        event_id=event_id,
        ticker=ticker,
        stage=stage,
        error_type=type(error).__name__,
        message=message[:MAX_MESSAGE_LENGTH],
    )


def resolve(
    session: Session,
    source: str,
    *,
    at: datetime,
    event_id: int | None = None,
    stage: str | None = None,
) -> int:
    """Та же задача отработала: её нерешённые ошибки — «решено», в журнал — одна запись «ok».

    Задача события — это (source, event_id, stage): успех у другого тикера чужую ошибку не решает.
    Ежедневная задача (без события) решает свои ошибки следующим успешным запуском.
    """
    query = select(orm.ErrorLog).where(
        orm.ErrorLog.level == "error",
        orm.ErrorLog.resolved_at.is_(None),
        orm.ErrorLog.source == source,
    )
    if event_id is None:
        query = query.where(orm.ErrorLog.event_id.is_(None))
    else:
        query = query.where(orm.ErrorLog.event_id == event_id, orm.ErrorLog.stage == stage)
    errors = session.scalars(query).all()
    if not errors:
        return 0
    for error in errors:
        error.resolved_at = at
    ticker = errors[0].ticker
    where = " ".join(part for part in (ticker, stage) if part)
    session.add(
        orm.ErrorLog(
            at=at,
            level="ok",
            source=source,
            event_id=event_id,
            ticker=ticker,
            stage=stage,
            error_type="OK",
            message=f"Решено{f': {where}' if where else ''} — задача отработала успешно.",
        )
    )
    return len(errors)


def logged_job[**P, R](
    source: str, engine: Callable[[], Engine]
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Ежедневная задача планировщика: ошибка пишется в журнал и пробрасывается дальше."""

    def decorate(job: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(job)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                result = job(*args, **kwargs)
            except Exception as error:
                try:
                    with Session(engine()) as session, session.begin():
                        session.add(error_entry(source, error, at=datetime.now(UTC)))
                except Exception:  # журнал не должен прятать исходную ошибку
                    logger.exception("error log write failed", extra={"source": source})
                raise
            try:
                with Session(engine()) as session, session.begin():
                    resolve(session, source, at=datetime.now(UTC))
            except Exception:  # журнал не должен ломать успешную задачу
                logger.exception("error log write failed", extra={"source": source})
            return result

        return wrapper

    return decorate
