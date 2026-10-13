"""Клиент Finnhub: календарь отчётов и история EPS (замена Benzinga, SPEC §6)."""

from datetime import date

import httpx
from pydantic import ValidationError

from adapters.api_model import ApiModel, require_env
from adapters.cache import Cache
from adapters.errors import DataError
from adapters.finnhub.models import FinnhubEarning, FinnhubEpsResult
from adapters.http import JsonHttpClient, Params, RetryPolicy
from core.config.sources import FinnhubSettings

SOURCE = "finnhub"


def finnhub_api_key() -> str:
    """FINNHUB_API_KEY из окружения."""
    return require_env("FINNHUB_API_KEY")


class FinnhubClient:
    def __init__(self, http: JsonHttpClient, settings: FinnhubSettings) -> None:
        self._http = http
        self._settings = settings

    @classmethod
    def create(
        cls,
        settings: FinnhubSettings,
        api_key: str,
        cache: Cache | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> "FinnhubClient":
        """По документации ключ передаётся только параметром token — он маскируется в логах."""
        http = JsonHttpClient(
            source=SOURCE,
            base_url=settings.base_url,
            secret_params={"token": api_key},
            timeout_seconds=settings.timeout_seconds,
            retry=RetryPolicy(settings.max_attempts, settings.backoff_base_seconds),
            cache=cache,
            transport=transport,
        )
        return cls(http, settings)

    def earnings_calendar(
        self, start: date, end: date, symbol: str | None = None
    ) -> list[FinnhubEarning]:
        """Отчёты в окне дат (все компании или одна)."""
        params: Params = {"from": start.isoformat(), "to": end.isoformat()}
        if symbol is not None:
            params = {**params, "symbol": symbol}
        payload = self._http.get_json(
            "/calendar/earnings", params, self._settings.cache_ttl_seconds.earnings_calendar
        )
        rows = payload.get("earningsCalendar")
        if not isinstance(rows, list):
            raise DataError(SOURCE, "expected an earningsCalendar list")
        return [_parse(FinnhubEarning, row) for row in rows]

    def earnings_history(self, symbol: str, limit: int | None = None) -> list[FinnhubEpsResult]:
        """Факт против оценки по кварталам (бесплатно — последние 4 квартала)."""
        params: Params = {"symbol": symbol}
        if limit is not None:
            params = {**params, "limit": limit}
        rows = self._http.get_json_list(
            "/stock/earnings", params, self._settings.cache_ttl_seconds.earnings_history
        )
        return [_parse(FinnhubEpsResult, row) for row in rows]


def _parse[M: ApiModel](model: type[M], data: object) -> M:
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise DataError(
            SOURCE, f"unexpected {model.__name__} shape: {exc.error_count()} error(s)"
        ) from exc
