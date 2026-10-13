"""Клиент Alpha Vantage: EARNINGS_CALENDAR, EARNINGS_ESTIMATES, EARNINGS (SPEC §6).

Ошибки и лимиты Alpha Vantage приходят кодом 200 с полем Information / Note / Error Message
(в CSV — вместо строк данных). Такой ответ — DataError и в кэш не попадает.
"""

import csv
import io
from typing import Any

import httpx
from pydantic import ValidationError

from adapters.alphavantage.models import (
    CALENDAR_COLUMNS,
    AvCalendarRow,
    AvEarnings,
    AvEstimate,
)
from adapters.api_model import BlankAsNoneModel, require_env
from adapters.cache import Cache
from adapters.errors import DataError
from adapters.http import JsonHttpClient, Params, RetryPolicy
from core.config.sources import AlphaVantageSettings

SOURCE = "alphavantage"
QUERY_PATH = "/query"
NOTICE_KEYS = ("Information", "Note", "Error Message")
NOTICE_PREVIEW = 200


def alphavantage_api_key() -> str:
    """ALPHAVANTAGE_API_KEY из окружения."""
    return require_env("ALPHAVANTAGE_API_KEY")


class AlphaVantageClient:
    def __init__(self, http: JsonHttpClient, settings: AlphaVantageSettings) -> None:
        self._http = http
        self._settings = settings

    @classmethod
    def create(
        cls,
        settings: AlphaVantageSettings,
        api_key: str,
        cache: Cache | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> "AlphaVantageClient":
        """Ключ передаётся параметром apikey (другого способа API не даёт) и маскируется в логах."""
        http = JsonHttpClient(
            source=SOURCE,
            base_url=settings.base_url,
            secret_params={"apikey": api_key},
            timeout_seconds=settings.timeout_seconds,
            retry=RetryPolicy(settings.max_attempts, settings.backoff_base_seconds),
            cache=cache,
            transport=transport,
        )
        return cls(http, settings)

    def earnings_calendar(self, symbol: str | None = None) -> list[AvCalendarRow]:
        """Предстоящие отчёты (весь рынок одним запросом или одна компания)."""
        params: Params = {
            "function": "EARNINGS_CALENDAR",
            "horizon": self._settings.calendar_horizon,
        }
        if symbol is not None:
            params = {**params, "symbol": symbol}
        text = self._http.get_text(
            QUERY_PATH, params, self._settings.cache_ttl_seconds.earnings_calendar, _check_calendar
        )
        return _parse_calendar(text)

    def earnings_estimates(self, symbol: str) -> list[AvEstimate]:
        """Консенсус по фискальным кварталам и годам с пересмотрами 7/30/60/90 дней."""
        payload = self._http.get_json(
            QUERY_PATH,
            {"function": "EARNINGS_ESTIMATES", "symbol": symbol},
            self._settings.cache_ttl_seconds.earnings_estimates,
            _reject_notice,
        )
        rows = payload.get("estimates")
        if not isinstance(rows, list):
            raise DataError(SOURCE, f"{symbol}: expected an estimates list")
        return [_validate(AvEstimate, row) for row in rows]

    def earnings(self, symbol: str) -> AvEarnings:
        """История EPS по кварталам: факт, оценка, сюрприз, время отчёта."""
        payload = self._http.get_json(
            QUERY_PATH,
            {"function": "EARNINGS", "symbol": symbol},
            self._settings.cache_ttl_seconds.earnings,
            _reject_notice,
        )
        return _validate(AvEarnings, payload)


def _reject_notice(payload: dict[str, Any]) -> None:
    for key in NOTICE_KEYS:
        if key in payload:
            raise DataError(SOURCE, f"{key}: {str(payload[key])[:NOTICE_PREVIEW]}")


def _check_calendar(text: str) -> None:
    """Проверка до кэширования: заглушка вместо CSV не должна попасть в кэш."""
    _parse_calendar(text)


def _parse_calendar(text: str) -> list[AvCalendarRow]:
    if text.lstrip().startswith("{"):
        raise DataError(SOURCE, f"notice instead of CSV: {text.strip()[:NOTICE_PREVIEW]}")
    reader = csv.DictReader(io.StringIO(text))
    if tuple(reader.fieldnames or ()) != CALENDAR_COLUMNS:
        raise DataError(SOURCE, f"unexpected calendar header: {reader.fieldnames}")
    return [_validate(AvCalendarRow, row) for row in reader]


def _validate[M: BlankAsNoneModel](model: type[M], data: object) -> M:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise DataError(
            SOURCE, f"unexpected {model.__name__} shape: {exc.error_count()} error(s)"
        ) from exc
