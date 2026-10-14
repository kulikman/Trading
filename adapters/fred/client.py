"""Клиент FRED: наблюдения рядов (VIXCLS, DGS10) для агента «Макро» (SPEC §6, §8)."""

from datetime import date
from typing import Any, Protocol

import httpx
from pydantic import Field, ValidationError, field_validator

from adapters.api_model import ApiModel, require_env
from adapters.cache import Cache
from adapters.errors import DataError
from adapters.http import JsonHttpClient, Params, RetryPolicy
from core.config.sources import FredSettings

SOURCE = "fred"
VIX = "VIXCLS"
US10Y = "DGS10"


def fred_api_key() -> str:
    """FRED_API_KEY из окружения."""
    return require_env("FRED_API_KEY")


class FredObservation(ApiModel):
    """value в ответе — строка. Нечисловое значение — None.

    TODO(OPEN_QUESTIONS): как FRED обозначает пропуск, в документации не сказано (обычно ".").
    """

    date: date
    value: float | None = Field(default=None)

    @field_validator("value", mode="before")
    @classmethod
    def _numeric_or_none(cls, raw: Any) -> Any:
        if isinstance(raw, str):
            try:
                return float(raw)
            except ValueError:
                return None
        return raw


class FredSource(Protocol):
    def observations(
        self, series_id: str, start: date | None = None, end: date | None = None
    ) -> list[FredObservation]:
        """Наблюдения ряда за период."""


class FredClient:
    def __init__(self, http: JsonHttpClient, settings: FredSettings) -> None:
        self._http = http
        self._settings = settings

    @classmethod
    def create(
        cls,
        settings: FredSettings,
        api_key: str,
        cache: Cache | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> "FredClient":
        """Ключ — параметром api_key (так в документации), маскируется в логах."""
        http = JsonHttpClient(
            source=SOURCE,
            base_url=settings.base_url,
            secret_params={"api_key": api_key},
            timeout_seconds=settings.timeout_seconds,
            retry=RetryPolicy(settings.max_attempts, settings.backoff_base_seconds),
            cache=cache,
            transport=transport,
        )
        return cls(http, settings)

    def observations(
        self, series_id: str, start: date | None = None, end: date | None = None
    ) -> list[FredObservation]:
        """Наблюдения ряда по возрастанию даты."""
        params: Params = {"series_id": series_id, "file_type": "json", "sort_order": "asc"}
        if start is not None:
            params = {**params, "observation_start": start.isoformat()}
        if end is not None:
            params = {**params, "observation_end": end.isoformat()}
        payload = self._http.get_json(
            "/fred/series/observations", params, self._settings.cache_ttl_seconds.observations
        )
        rows = payload.get("observations")
        if not isinstance(rows, list):
            raise DataError(SOURCE, f"{series_id}: expected an observations list")
        try:
            return [FredObservation.model_validate(row) for row in rows]
        except ValidationError as exc:
            raise DataError(SOURCE, f"{series_id}: unexpected observation shape") from exc

    def latest(self, series_id: str, as_of: date, lookback_days: int) -> FredObservation:
        """Последнее непустое значение не позже as_of. Нет — DataError (не угадываем)."""
        start = date.fromordinal(as_of.toordinal() - lookback_days)
        values = [o for o in self.observations(series_id, start, as_of) if o.value is not None]
        if not values:
            raise DataError(SOURCE, f"{series_id}: no value in {lookback_days} days before {as_of}")
        return values[-1]
