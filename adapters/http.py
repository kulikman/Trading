"""HTTP-клиент адаптеров: JSON, повторы с backoff, кэш, сырой ответ в debug-лог (SPEC §6)."""

import hashlib
import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from adapters.cache import Cache
from adapters.errors import DataError

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
ERROR_BODY_PREVIEW = 200

Params = Mapping[str, str | int | float | bool]


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    backoff_base_seconds: float

    def delay(self, attempt: int) -> float:
        """Пауза перед повтором: base, 2·base, 4·base…"""
        return float(self.backoff_base_seconds * 2 ** (attempt - 1))


class JsonHttpClient:
    """Секреты передаются только заголовками и не попадают в лог, ключ кэша и ошибки."""

    def __init__(
        self,
        *,
        source: str,
        base_url: str,
        headers: Mapping[str, str],
        timeout_seconds: float,
        retry: RetryPolicy,
        cache: Cache | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._source = source
        self._client = httpx.Client(
            base_url=base_url, headers=dict(headers), timeout=timeout_seconds, transport=transport
        )
        self._retry = retry
        self._cache = cache
        self._sleep = sleep

    def get_json(
        self, path_or_url: str, params: Params | None = None, ttl_seconds: int = 0
    ) -> dict[str, Any]:
        """GET и разбор JSON-объекта. ttl_seconds = 0 — без кэша."""
        request = self._client.build_request("GET", path_or_url, params=_stringify(params))
        url = str(request.url)
        key = hashlib.sha256(url.encode()).hexdigest()
        if self._cache is not None and ttl_seconds > 0:
            cached = self._cache.get(key)
            if cached is not None:
                return _parse(self._source, url, cached)
        body = self._send(request, url)
        payload = _parse(self._source, url, body)
        if self._cache is not None and ttl_seconds > 0:
            self._cache.set(key, body, ttl_seconds)
        return payload

    def _send(self, request: httpx.Request, url: str) -> bytes:
        for attempt in range(1, self._retry.max_attempts + 1):
            is_last = attempt == self._retry.max_attempts
            try:
                response = self._client.send(request)
            except httpx.TransportError as exc:
                if is_last:
                    raise DataError(self._source, f"{type(exc).__name__} on {url}") from exc
                self._sleep(self._retry.delay(attempt))
                continue
            logger.debug(
                "raw response",
                extra={
                    "source": self._source,
                    "url": url,
                    "status": response.status_code,
                    "body": response.text,
                },
            )
            if response.is_success:
                return response.content
            if response.status_code not in RETRYABLE_STATUS or is_last:
                preview = response.text[:ERROR_BODY_PREVIEW]
                raise DataError(self._source, f"HTTP {response.status_code} on {url}: {preview}")
            self._sleep(self._retry.delay(attempt))
        raise AssertionError("unreachable: the last attempt returns or raises")  # pragma: no cover

    def close(self) -> None:
        """Закрыть соединения."""
        self._client.close()


def _stringify(params: Params | None) -> dict[str, str] | None:
    if params is None:
        return None
    return {k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in params.items()}


def _parse(source: str, url: str, body: bytes) -> dict[str, Any]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise DataError(source, f"invalid JSON from {url}") from exc
    if not isinstance(payload, dict):
        raise DataError(source, f"expected a JSON object from {url}")
    return payload
