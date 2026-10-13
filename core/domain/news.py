"""Новость о компании (для профиля компании и агентов, DASHBOARD.md §4.5)."""

from typing import Any

from pydantic import AwareDatetime, Field

from core.domain.base import DomainModel


class NewsItem(DomainModel):
    id: str  # идентификатор источника
    source: str
    published_at: AwareDatetime
    title: str
    url: str
    tickers: list[str] = Field(min_length=1)
    publisher: str | None = None
    author: str | None = None
    description: str | None = None
    keywords: list[str] | None = None
    insights: list[dict[str, Any]] | None = None  # тональность от источника, не наша модель
    # LLM-разметка (T14): менеджмент / регуляторика / M&A / конкуренты.
    tags: list[str] | None = None
