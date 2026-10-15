"""Сообщения «СИСТЕМА» (SPEC §12, T18): журнал в system_message и отправка в Telegram.

Источники сообщений: части системы (`DbSystemNotifier`, например расхождение дат календаря) и
журнал ошибок задач — одно сообщение на начало сбоя задачи и одно на «снова работает» (не на каждый
повтор). Отправляет диспетчер; отправленное помечается и не повторяется.
Состояние источников данных (adapters.health) переносится в source_status там же.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.health import SourceHealth
from core.db import models as orm

logger = logging.getLogger(__name__)

MAX_DETAIL = 300


class SystemNotifier(Protocol):
    def system(self, text: str, *, code: str | None = None) -> None:
        """Сообщение «СИСТЕМА»: сбой данных, расхождение, молчание сервиса."""


class Sender(Protocol):
    def send(self, text: str) -> int:
        """Отправить сообщение; вернуть его id."""


class LoggingNotifier:
    def system(self, text: str, *, code: str | None = None) -> None:
        logger.warning("SYSTEM: %s", text, extra={"code": code})


class DbSystemNotifier:
    """Пишет сообщение в журнал своей транзакцией; в Telegram его отправит диспетчер."""

    def __init__(
        self,
        session_factory: Callable[[], Session],
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._session = session_factory
        self._clock = clock

    def system(self, text: str, *, code: str | None = None) -> None:
        logger.warning("SYSTEM: %s", text, extra={"code": code})
        with self._session() as session, session.begin():
            session.add(orm.SystemMessage(at=self._clock(), code=code, text=text))


def collect_error_messages(session: Session) -> int:
    """Новые строки журнала ошибок → сообщения: первый сбой задачи и её восстановление."""
    rows = session.scalars(
        select(orm.ErrorLog).where(orm.ErrorLog.notified_at.is_(None)).order_by(orm.ErrorLog.id)
    ).all()
    created = 0
    for row in rows:
        if row.level == "ok":
            text = f"СИСТЕМА · {row.source}: снова работает"
        elif _already_failing(session, row):
            text = None  # сбой этой задачи уже объявлен — повтор не шлём
        else:
            where = " ".join(p for p in (row.source, row.ticker, row.stage) if p)
            text = f"СИСТЕМА · сбой {where}: {row.error_type}: {row.message[:MAX_DETAIL]}"
        if text is not None:
            session.add(orm.SystemMessage(at=row.at, code=row.error_type, text=text))
            created += 1
        row.notified_at = row.at
    session.flush()
    return created


def save_source_health(session: Session, snapshot: dict[str, SourceHealth]) -> None:
    """Состояние источников из процесса → source_status (более поздние отметки не затираются)."""
    for source, health in snapshot.items():
        row = session.get(orm.SourceStatus, source) or orm.SourceStatus(source=source)
        if health.last_ok_at and (row.last_ok_at is None or health.last_ok_at > row.last_ok_at):
            row.last_ok_at = health.last_ok_at
        if health.last_error_at and (
            row.last_error_at is None or health.last_error_at > row.last_error_at
        ):
            row.last_error_at, row.last_error = health.last_error_at, health.last_error
        session.add(row)
    session.flush()


def send_system_messages(session: Session, client: Sender, now: datetime) -> int:
    """Отправить неотправленные; каждое фиксируется сразу — сбой на следующем его не повторит."""
    rows = session.scalars(
        select(orm.SystemMessage)
        .where(orm.SystemMessage.sent_at.is_(None))
        .order_by(orm.SystemMessage.id)
    ).all()
    sent = 0
    for row in rows:
        row.tg_message_id = client.send(row.text)
        row.sent_at = now
        session.commit()
        sent += 1
    return sent


def _already_failing(session: Session, row: orm.ErrorLog) -> bool:
    """У задачи уже есть объявленный и не решённый сбой."""
    found = session.scalar(
        select(orm.ErrorLog.id)
        .where(
            orm.ErrorLog.source == row.source,
            orm.ErrorLog.level == "error",
            orm.ErrorLog.id != row.id,
            orm.ErrorLog.notified_at.is_not(None),
            orm.ErrorLog.resolved_at.is_(None),
        )
        .limit(1)
    )
    return found is not None
