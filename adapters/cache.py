"""Кэш ответов адаптеров: Redis в работе, память в тестах."""

import logging
import os
import time
from collections.abc import Callable
from typing import Protocol

import redis
from redis.backoff import NoBackoff
from redis.retry import Retry

from core.config import ConfigError

logger = logging.getLogger(__name__)


class Cache(Protocol):
    def get(self, key: str) -> bytes | None: ...

    def set(self, key: str, value: bytes, ttl_seconds: int) -> None: ...


class RedisCache:
    """Сбой Redis не роняет запрос: промах кэша + предупреждение в лог."""

    def __init__(self, client: "redis.Redis", prefix: str = "earnings:") -> None:
        self._client = client
        self._prefix = prefix

    @classmethod
    def connect(cls, url: str, timeout_seconds: float) -> "RedisCache":
        """Короткий таймаут, без повторов redis-py: упавший Redis — быстрый промах, не зависание."""
        client = redis.Redis.from_url(
            url,
            socket_connect_timeout=timeout_seconds,
            socket_timeout=timeout_seconds,
            retry=Retry(NoBackoff(), 0),
        )
        return cls(client)

    @classmethod
    def from_env(cls, timeout_seconds: float) -> "RedisCache":
        """REDIS_URL из окружения; `make` подставляет локальный адрес из docker-compose."""
        url = os.environ.get("REDIS_URL", "").strip()
        if not url:
            raise ConfigError("REDIS_URL is not set: run `make db-up` and use `make test`")
        return cls.connect(url, timeout_seconds)

    def get(self, key: str) -> bytes | None:
        try:
            value = self._client.get(self._prefix + key)
        except redis.RedisError as exc:
            logger.warning("cache get failed", extra={"key": key, "error": str(exc)})
            return None
        return value if isinstance(value, bytes) else None

    def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        try:
            self._client.set(self._prefix + key, value, ex=ttl_seconds)
        except redis.RedisError as exc:
            logger.warning("cache set failed", extra={"key": key, "error": str(exc)})


class MemoryCache:
    """Кэш в памяти процесса — для тестов и локальных прогонов."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._items: dict[str, tuple[float, bytes]] = {}

    def get(self, key: str) -> bytes | None:
        item = self._items.get(key)
        if item is None:
            return None
        expires_at, value = item
        if self._clock() >= expires_at:
            del self._items[key]
            return None
        return value

    def set(self, key: str, value: bytes, ttl_seconds: int) -> None:
        self._items[key] = (self._clock() + ttl_seconds, value)
