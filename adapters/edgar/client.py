"""Клиент SEC EDGAR: CIK по тикеру, подачи 8-K / 10-Q / 10-K, XBRL companyfacts (SPEC §6)."""

from collections.abc import Collection
from datetime import date
from typing import Any

import httpx
from pydantic import ValidationError

from adapters.api_model import require_env
from adapters.cache import Cache
from adapters.edgar.models import CompanyFacts, Filing
from adapters.errors import DataError
from adapters.http import JsonHttpClient, RetryPolicy
from core.config.sources import EdgarSettings

SOURCE = "edgar"
PERIODIC_FORMS = frozenset({"8-K", "10-Q", "10-K"})


def sec_user_agent() -> str:
    """SEC_USER_AGENT: название и контактный email (требование SEC к автоматическим запросам)."""
    return require_env("SEC_USER_AGENT")


def cik10(cik: int) -> str:
    return f"CIK{cik:010d}"


class EdgarClient:
    def __init__(self, http: JsonHttpClient, settings: EdgarSettings) -> None:
        self._http = http
        self._settings = settings

    @classmethod
    def create(
        cls,
        settings: EdgarSettings,
        user_agent: str,
        cache: Cache | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> "EdgarClient":
        http = JsonHttpClient(
            source=SOURCE,
            base_url=settings.data_base_url,
            headers={"User-Agent": user_agent},
            timeout_seconds=settings.timeout_seconds,
            retry=RetryPolicy(settings.max_attempts, settings.backoff_base_seconds),
            cache=cache,
            transport=transport,
        )
        return cls(http, settings)

    def ticker_ciks(self) -> dict[str, int]:
        """Тикер → CIK (www.sec.gov; без контакта в User-Agent — 403)."""
        payload = self._http.get_json(
            self._settings.tickers_url, ttl_seconds=self._settings.cache_ttl_seconds.tickers
        )
        mapping: dict[str, int] = {}
        for row in payload.values():
            if not isinstance(row, dict) or "ticker" not in row or "cik_str" not in row:
                raise DataError(SOURCE, "unexpected company_tickers row")
            mapping[str(row["ticker"]).upper()] = int(row["cik_str"])
        return mapping

    def filings(self, cik: int, forms: Collection[str] = PERIODIC_FORMS) -> list[Filing]:
        """Недавние подачи компании нужных форм, от новых к старым.

        Только блок `recent` (около 1000 последних подач); старые страницы `files` не читаются.
        """
        payload = self._http.get_json(
            f"/submissions/{cik10(cik)}.json",
            ttl_seconds=self._settings.cache_ttl_seconds.submissions,
        )
        recent = payload.get("filings", {}).get("recent")
        if not isinstance(recent, dict):
            raise DataError(SOURCE, f"{cik10(cik)}: no filings.recent")
        return [f for f in _rows(cik, recent) if f.form in forms]

    def earnings_releases(self, cik: int, since: date | None = None) -> list[Filing]:
        """8-K с пунктом 2.02 — пресс-релиз о результатах (источник для «Досье» и guidance)."""
        item = self._settings.earnings_release_item
        return [
            f
            for f in self.filings(cik, {"8-K"})
            if item in f.items and (since is None or f.filing_date >= since)
        ]

    def company_facts(self, cik: int) -> CompanyFacts:
        """XBRL-факты компании (около 6 МБ на крупного эмитента — кэшируется на сутки)."""
        payload = self._http.get_json(
            f"/api/xbrl/companyfacts/{cik10(cik)}.json",
            ttl_seconds=self._settings.cache_ttl_seconds.company_facts,
        )
        try:
            return CompanyFacts.model_validate(payload)
        except ValidationError as exc:
            raise DataError(SOURCE, f"{cik10(cik)}: unexpected companyfacts shape") from exc


def _rows(cik: int, recent: dict[str, Any]) -> list[Filing]:
    columns = {
        "form": "form",
        "accessionNumber": "accession_number",
        "filingDate": "filing_date",
        "reportDate": "report_date",
        "acceptanceDateTime": "accepted_at",
        "primaryDocument": "primary_document",
        "items": "items",
    }
    arrays: dict[str, list[Any]] = {}
    for key in columns:
        column = recent.get(key)
        if not isinstance(column, list):
            raise DataError(SOURCE, f"{cik10(cik)}: filings.recent is missing column {key}")
        arrays[key] = column
    lengths = {len(column) for column in arrays.values()}
    if len(lengths) != 1:
        raise DataError(SOURCE, f"{cik10(cik)}: filings.recent columns differ in length")
    count = lengths.pop()
    filings: list[Filing] = []
    for i in range(count):
        row: dict[str, Any] = {"cik": cik}
        for key, field in columns.items():
            row[field] = arrays[key][i]
        try:
            filings.append(Filing.model_validate(row))
        except ValidationError as exc:
            raise DataError(SOURCE, f"{cik10(cik)}: unexpected filing row {i}") from exc
    return filings
