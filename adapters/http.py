"""HTTP-клиент адаптеров: JSON, повторы с backoff, кэш, сырой ответ в debug-лог (SPEC §6)."""

import hashlib
import json
import logging
import time
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from adapters.cache import Cache
from adapters.errors import DataError

logger = logging.getLogger(__name__)

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
ERROR_BODY_PREVIEW = 200
REDACTED = "***"

Params = Mapping[str, str | int | float | bool]


class RateLimiter:
    """Не больше max_requests запросов за period_seconds (скользящее окно).

    Нужен там, где лимит в минуту, а не в секунду: короткие повторы при 429 его не обходят.
    """

    def __init__(
        self,
        max_requests: int,
        period_seconds: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_requests < 1 or period_seconds <= 0:
            raise ValueError("rate limit needs max_requests >= 1 and period_seconds > 0")
        self._max = max_requests
        self._period = period_seconds
        self._clock = clock
        self._sleep = sleep
        self._sent: deque[float] = deque()

    def __call__(self) -> None:
        """Подождать, если окно заполнено, и учесть запрос."""
        now = self._clock()
        while self._sent and self._sent[0] <= now - self._period:
            self._sent.popleft()
        if len(self._sent) >= self._max:
            wait = self._sent[0] + self._period - now
            logger.debug("rate limit: waiting", extra={"wait_seconds": round(wait, 1)})
            self._sleep(wait)
            now = self._clock()
            self._sent.popleft()
        self._sent.append(now)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int
    backoff_base_seconds: float

    def delay(self, attempt: int) -> float:
        """Пауза перед повтором: base, 2·base, 4·base…"""
        return float(self.backoff_base_seconds * 2 ** (attempt - 1))


class JsonHttpClient:
    """Секреты — в заголовках или secret_params; в лог, ошибки и ключ кэша не попадают."""

    def __init__(
        self,
        *,
        source: str,
        base_url: str,
        headers: Mapping[str, str] | None = None,
        timeout_seconds: float,
        retry: RetryPolicy,
        cache: Cache | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        secret_params: Mapping[str, str] | None = None,
        throttle: Callable[[], None] | None = None,
    ) -> None:
        self._source = source
        self._throttle = throttle
        self._client = httpx.Client(
            base_url=base_url,
            headers=dict(headers or {}),
            params=dict(secret_params or {}),
            timeout=timeout_seconds,
            transport=transport,
        )
        self._secrets = [value for value in (secret_params or {}).values() if value]
        self._retry = retry
        self._cache = cache
        self._sleep = sleep

    def get_json(
        self,
        path_or_url: str,
        params: Params | None = None,
        ttl_seconds: int = 0,
        validate: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """GET и разбор JSON-объекта. ttl_seconds = 0 — без кэша.

        validate бросает DataError на ответ-заглушку; такой ответ не кэшируется.
        """

        def parse(body: bytes, url: str) -> dict[str, Any]:
            payload = self._load_json(body, url)
            if not isinstance(payload, dict):
                raise DataError(self._source, f"expected a JSON object from {url}")
            if validate is not None:
                validate(payload)
            return payload

        return self._get(path_or_url, params, ttl_seconds, parse)

    def get_json_list(
        self, path_or_url: str, params: Params | None = None, ttl_seconds: int = 0
    ) -> list[Any]:
        """GET и разбор JSON-массива на верхнем уровне."""

        def parse(body: bytes, url: str) -> list[Any]:
            payload = self._load_json(body, url)
            if not isinstance(payload, list):
                raise DataError(self._source, f"expected a JSON array from {url}")
            return payload

        return self._get(path_or_url, params, ttl_seconds, parse)

    def get_text(
        self,
        path_or_url: str,
        params: Params | None = None,
        ttl_seconds: int = 0,
        validate: Callable[[str], None] | None = None,
    ) -> str:
        """GET текста (например, CSV); validate — как у get_json."""

        def parse(body: bytes, url: str) -> str:
            try:
                text = body.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise DataError(self._source, f"non-UTF-8 text from {url}") from exc
            if validate is not None:
                validate(text)
            return text

        return self._get(path_or_url, params, ttl_seconds, parse)

    def _load_json(self, body: bytes, url: str) -> Any:
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise DataError(self._source, f"invalid JSON from {url}") from exc

    def _get[T](
        self, path_or_url: str, params: Params | None, ttl: int, parse: Callable[[bytes, str], T]
    ) -> T:
        """Кэшируется только ответ, который прошёл разбор и проверку."""
        request = self._client.build_request("GET", path_or_url, params=_stringify(params))
        url = self._redact(str(request.url))
        key = hashlib.sha256(url.encode()).hexdigest()
        use_cache = self._cache is not None and ttl > 0
        if use_cache and self._cache is not None:
            cached = self._cache.get(key)
            if cached is not None:
                return parse(cached, url)
        body = self._send(request, url)
        result = parse(body, url)
        if use_cache and self._cache is not None:
            self._cache.set(key, body, ttl)
        return result

    def _redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        return text

    def _send(self, request: httpx.Request, url: str) -> bytes:
        for attempt in range(1, self._retry.max_attempts + 1):
            is_last = attempt == self._retry.max_attempts
            if self._throttle is not None:
                self._throttle()  # только сетевые запросы: ответ из кэша лимит не тратит
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
                    "body": self._redact(response.text),
                },
            )
            if response.is_success:
                return response.content
            if response.status_code not in RETRYABLE_STATUS or is_last:
                preview = self._redact(response.text[:ERROR_BODY_PREVIEW])
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
