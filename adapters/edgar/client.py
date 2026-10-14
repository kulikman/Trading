"""Клиент SEC EDGAR: CIK по тикеру, подачи 8-K / 10-Q / 10-K, XBRL companyfacts (SPEC §6)."""

from collections.abc import Collection
from datetime import date
from typing import Any

import httpx
from pydantic import ValidationError

from adapters.api_model import require_env
from adapters.cache import Cache
from adapters.edgar.documents import FilingDocument, submission_documents
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

    def filings(
        self, cik: int, forms: Collection[str] = PERIODIC_FORMS, since: date | None = None
    ) -> list[Filing]:
        """Подачи компании нужных форм, от новых к старым.

        Блок `recent` — около 1000 последних подач (у банков с тысячами выпусков нот — меньше года).
        С since дочитываются старые страницы `files`, перекрывающие период; они не меняются и
        кэшируются надолго.
        """
        payload = self._http.get_json(
            f"/submissions/{cik10(cik)}.json",
            ttl_seconds=self._settings.cache_ttl_seconds.submissions,
        )
        filings_node = payload.get("filings", {})
        recent = filings_node.get("recent")
        if not isinstance(recent, dict):
            raise DataError(SOURCE, f"{cik10(cik)}: no filings.recent")
        rows = _rows(cik, recent)
        if since is not None:
            for name in _older_pages(cik, filings_node.get("files", []), since):
                page = self._http.get_json(
                    f"/submissions/{name}",
                    ttl_seconds=self._settings.cache_ttl_seconds.submissions_history,
                )
                rows += _rows(cik, page)
        return [f for f in rows if f.form in forms and (since is None or f.filing_date >= since)]

    def earnings_releases(self, cik: int, since: date | None = None) -> list[Filing]:
        """8-K с пунктом 2.02 — пресс-релиз о результатах (источник для «Досье» и guidance)."""
        item = self._settings.earnings_release_item
        return [f for f in self.filings(cik, {"8-K"}, since) if item in f.items]

    def documents(self, filing: Filing) -> list[FilingDocument]:
        """Текстовые документы подачи: полный текст с www.sec.gov (не меняется — долгий кэш)."""
        folder = filing.accession_number.replace("-", "")
        url = (
            f"{self._settings.archives_base_url}/{filing.cik}/{folder}/"
            f"{filing.accession_number}.txt"
        )
        text = self._http.get_text(url, ttl_seconds=self._settings.cache_ttl_seconds.documents)
        return submission_documents(text)

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


def _older_pages(cik: int, files: object, since: date) -> list[str]:
    """Имена старых страниц подач, которые заканчиваются не раньше since."""
    if not isinstance(files, list):
        raise DataError(SOURCE, f"{cik10(cik)}: filings.files is not a list")
    names = []
    for page in files:
        if not isinstance(page, dict) or "name" not in page or "filingTo" not in page:
            raise DataError(SOURCE, f"{cik10(cik)}: unexpected filings.files entry")
        if date.fromisoformat(str(page["filingTo"])) >= since:
            names.append(str(page["name"]))
    return names


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
