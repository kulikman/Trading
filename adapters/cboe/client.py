"""CBOE: дневная история VIX (VIX_History.csv) — закрытие дня без задержки FRED (E2d).

FRED публикует VIXCLS больше чем через сутки (15.10.2026 09:35 ET последним было закрытие 13.10);
CBOE — владелец индекса — выкладывает закрытие в тот же вечер. Ключа не нужно; файл — вся
история, строки «MM/DD/YYYY,OPEN,HIGH,LOW,CLOSE».
"""

import csv
import io
from datetime import date
from typing import Protocol

import httpx

from adapters.cache import Cache
from adapters.errors import DataError
from adapters.http import JsonHttpClient, RetryPolicy
from core.config.sources import CboeSettings

SOURCE = "cboe"
VIX_HISTORY = "/api/global/us_indices/daily_prices/VIX_History.csv"


class VixSource(Protocol):
    def vix_closes(self, start: date, end: date) -> dict[date, float]:
        """Закрытия VIX за [start, end]."""


class CboeClient:
    def __init__(self, http: JsonHttpClient, settings: CboeSettings) -> None:
        self._http = http
        self._settings = settings

    @classmethod
    def create(
        cls,
        settings: CboeSettings,
        cache: Cache | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> "CboeClient":
        http = JsonHttpClient(
            source=SOURCE,
            base_url=settings.base_url,
            headers={"User-Agent": settings.user_agent},
            timeout_seconds=settings.timeout_seconds,
            retry=RetryPolicy(settings.max_attempts, settings.backoff_base_seconds),
            cache=cache,
            transport=transport,
        )
        return cls(http, settings)

    def vix_closes(self, start: date, end: date) -> dict[date, float]:
        text = self._http.get_text(
            VIX_HISTORY, ttl_seconds=self._settings.cache_ttl_seconds.vix_history
        )
        return {d: v for d, v in parse_vix_history(text).items() if start <= d <= end}


def parse_vix_history(text: str) -> dict[date, float]:
    """CSV CBOE → {дата: закрытие}; неверная строка — DataError (формат сменился)."""
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or [c.strip().upper() for c in rows[0]][:5] != [
        "DATE",
        "OPEN",
        "HIGH",
        "LOW",
        "CLOSE",
    ]:
        raise DataError(SOURCE, "VIX_History.csv: unexpected header")
    out: dict[date, float] = {}
    for row in rows[1:]:
        if not row:
            continue
        try:
            month, day, year = (int(part) for part in row[0].strip().split("/"))
            out[date(year, month, day)] = float(row[4])
        except (ValueError, IndexError) as exc:
            raise DataError(SOURCE, f"VIX_History.csv: bad row {row[:5]}") from exc
    return out
