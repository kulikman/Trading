"""Клиент Financial Modeling Prep: analyst-estimates (fallback для consensus агента).

Используется только если Alpha Vantage не вернул данных. Бесплатный тариф:
250 запросов в день. Ключ — FMP_API_KEY (параметр apikey).

Revision-поля (7/30/90 дней назад) у FMP недоступны — будут None в AvEstimate.
estimate_dispersion и analyst_count работают.
"""

from typing import Any

import httpx
from pydantic import ValidationError

from adapters.alphavantage.models import AvEstimate
from adapters.api_model import require_env
from adapters.cache import Cache
from adapters.errors import DataError
from adapters.fmp.models import FmpEstimateRow
from adapters.http import JsonHttpClient, RetryPolicy
from core.config.sources import FmpSettings

SOURCE = "fmp"
ESTIMATES_PATH = "/api/v3/analyst-estimates/{symbol}"


def fmp_api_key() -> str:
    """FMP_API_KEY из окружения."""
    return require_env("FMP_API_KEY")


class FmpClient:
    def __init__(self, http: JsonHttpClient, settings: FmpSettings) -> None:
        self._http = http
        self._settings = settings

    @classmethod
    def create(
        cls,
        settings: FmpSettings,
        api_key: str,
        cache: Cache | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> "FmpClient":
        """Ключ передаётся параметром apikey и маскируется в логах."""
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

    def earnings_estimates(self, symbol: str) -> list[AvEstimate]:
        """Квартальные оценки аналитиков — последние limit кварталов."""
        payload = self._http.get_json(
            ESTIMATES_PATH.format(symbol=symbol),
            {"period": "quarter", "limit": self._settings.estimate_limit},
            self._settings.cache_ttl_seconds,
        )
        if not isinstance(payload, list):
            raise DataError(SOURCE, f"{symbol}: expected list, got {type(payload).__name__}")
        return [_parse(row) for row in payload]


def _parse(raw: Any) -> AvEstimate:
    try:
        return FmpEstimateRow.model_validate(raw).to_av_estimate()
    except ValidationError as exc:
        raise DataError(SOURCE, f"unexpected shape: {exc.error_count()} error(s)") from exc
