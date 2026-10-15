"""Состояние источников данных в процессе (T18, DASHBOARD §4.7): последний успех и последний сбой.

HTTP-клиенты отмечают каждый сетевой ответ (кэш не считается — он не доказывает, что источник жив).
Планировщик раз в цикл диспетчера переносит накопленное в таблицу source_status (`drain`).
"""

import threading
from dataclasses import dataclass
from datetime import UTC, datetime

_LOCK = threading.Lock()


@dataclass
class SourceHealth:
    last_ok_at: datetime | None = None
    last_error_at: datetime | None = None
    last_error: str | None = None


_STATE: dict[str, SourceHealth] = {}


def mark_ok(source: str, at: datetime | None = None) -> None:
    with _LOCK:
        _STATE.setdefault(source, SourceHealth()).last_ok_at = at or datetime.now(UTC)


def mark_error(source: str, detail: str, at: datetime | None = None) -> None:
    with _LOCK:
        health = _STATE.setdefault(source, SourceHealth())
        health.last_error_at = at or datetime.now(UTC)
        health.last_error = detail[:500]


def drain() -> dict[str, SourceHealth]:
    """Накопленное с прошлого раза; состояние в процессе очищается."""
    with _LOCK:
        snapshot = dict(_STATE)
        _STATE.clear()
    return snapshot
