"""Модели SEC EDGAR — по записанным ответам data.sec.gov (13.10.2026)."""

from datetime import date
from typing import Any

from pydantic import AwareDatetime, Field, field_validator

from adapters.api_model import ApiModel

MONEY_UNITS = ("USD", "USD/shares")


class Filing(ApiModel):
    """Одна подача из submissions.filings.recent (параллельные массивы, собранные в строку)."""

    cik: int
    form: str
    accession_number: str
    filing_date: date
    report_date: date | None = None
    accepted_at: AwareDatetime | None = None
    primary_document: str
    items: list[str] = Field(default_factory=list)

    @field_validator("report_date", "accepted_at", mode="before")
    @classmethod
    def _blank_to_none(cls, value: Any) -> Any:
        return value or None

    @field_validator("items", mode="before")
    @classmethod
    def _split_items(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    def url(self, archives_base_url: str) -> str:
        """Ссылка на основной документ подачи."""
        folder = self.accession_number.replace("-", "")
        return f"{archives_base_url}/{self.cik}/{folder}/{self.primary_document}"


class XbrlFact(ApiModel):
    """Факт companyfacts: значение за период (start..end) из конкретной подачи."""

    start: date | None = None
    end: date
    val: float
    accn: str
    fy: int | None = None
    fp: str | None = None
    form: str
    filed: date
    frame: str | None = None


class CompanyFacts(ApiModel):
    cik: int
    entity_name: str = Field(alias="entityName")
    facts: dict[str, dict[str, Any]]

    def concept(self, name: str) -> tuple[str, list[XbrlFact]] | None:
        """Факты us-gaap по тегу в денежных единицах: (единица, факты) или None, если тега нет."""
        node = self.facts.get("us-gaap", {}).get(name)
        if not isinstance(node, dict):
            return None
        units = node.get("units", {})
        for unit in MONEY_UNITS:
            if unit in units:
                return unit, [XbrlFact.model_validate(raw) for raw in units[unit]]
        return None
