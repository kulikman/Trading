"""Журнал задач (экран «Настройки → Логи»): что упало, когда и почему, и когда снова заработало.

После ошибки первый успешный запуск той же задачи пишет запись «ok» (одну, а не на каждый успех).

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


def recovery_entry(
    session: Session,
    source: str,
    *,
    at: datetime,
    event_id: int | None = None,
    ticker: str | None = None,
    stage: str | None = None,
) -> orm.ErrorLog | None:
    """Запись «снова работает», если последняя запись этой задачи — ошибка; иначе None."""
    last = session.scalars(
        select(orm.ErrorLog.level)
        .where(orm.ErrorLog.source == source)
        .order_by(orm.ErrorLog.at.desc(), orm.ErrorLog.id.desc())
        .limit(1)
    ).first()
    if last != "error":
        return None
    where = " ".join(part for part in (ticker, stage) if part)
    return orm.ErrorLog(
        at=at,
        level="ok",
        source=source,
        event_id=event_id,
        ticker=ticker,
        stage=stage,
        error_type="OK",
        message=f"Задача снова работает{f' ({where})' if where else ''}.",
    )


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
                    entry = recovery_entry(session, source, at=datetime.now(UTC))
                    if entry is not None:
                        session.add(entry)
            except Exception:  # журнал не должен ломать успешную задачу
                logger.exception("error log write failed", extra={"source": source})
            return result

        return wrapper

    return decorate
