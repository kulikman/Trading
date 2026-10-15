"""Новости компаний (E6, DASHBOARD §4.5 «Новости с прошлого отчёта»): сбор Massive и теги.

Каждый день: по компании вселенной — новости после последней сохранённой (первый раз — за
`first_days`), сохраняются без дублей. Теги — LLM, один вызов на компанию по новостям без тегов:
только четыре категории SPEC (менеджмент / регуляторика / M&A / конкуренты), пусто — «рутина».
Сбой LLM — теги остаются пустыми (NULL) и размечаются на следующий день.
"""

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal, Protocol

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from adapters.errors import DataError
from adapters.massive.models import NewsArticle, news_item
from core.db import models as orm
from core.db.store import save_news

logger = logging.getLogger(__name__)

Tag = Literal["менеджмент", "регуляторика", "M&A", "конкуренты"]
FIRST_DAYS = 30
MAX_TAGGED_PER_TICKER = 30


class NewsSource(Protocol):
    def news(self, ticker: str, published_gte: date | None = None) -> list[NewsArticle]:
        """Новости по тикеру."""


class Extractor(Protocol):
    def extract[M: BaseModel](self, *, instructions: str, text: str, schema: type[M]) -> M:
        """Извлечение по схеме."""


class TaggedItem(BaseModel):
    id: str = Field(description="Идентификатор новости из списка")
    tags: list[Tag] = Field(description="Категории; пусто — рутинная новость")


class Tagging(BaseModel):
    items: list[TaggedItem]


TAG_INSTRUCTIONS = """\
Below are news headlines about one US public company. Tag each headline with the categories that
apply, using ONLY these labels: "менеджмент" (management or board changes, executive statements
about strategy), "регуляторика" (regulators, lawsuits, investigations, government policy),
"M&A" (mergers, acquisitions, divestitures, stake purchases), "конкуренты" (competitors' moves
that matter for this company). Routine news (analyst ratings, price moves, generic market
commentary) gets an empty list. Each line is "[id] headline"; return every id (without
brackets) exactly once.
"""


@dataclass
class NewsRunResult:
    saved: int = 0
    tagged: int = 0
    failed: list[str] = field(default_factory=list)


def collect_news(
    session: Session,
    source: NewsSource,
    llm: Extractor | None,
    tickers: Iterable[str],
    today: date,
) -> NewsRunResult:
    """Новые статьи по каждой компании и теги к неразмеченным; сбой одной компании — не всего."""
    result = NewsRunResult()
    for ticker in tickers:
        latest = session.scalar(
            select(func.max(orm.NewsArticle.published_at)).where(
                orm.NewsArticle.tickers.contains([ticker])
            )
        )
        since = latest.date() if latest is not None else today - timedelta(days=FIRST_DAYS)
        try:
            articles = source.news(ticker, published_gte=since)
        except DataError as exc:
            logger.warning("news failed", extra={"ticker": ticker, "error": str(exc)})
            result.failed.append(ticker)
            continue
        result.saved += save_news(session, (news_item(a) for a in articles))
        session.commit()  # сохранённое не теряется при сбое следующей компании
        if llm is not None:
            result.tagged += _tag(session, llm, ticker, today)
    return result


def _tag(session: Session, llm: Extractor, ticker: str, today: date) -> int:
    rows = session.scalars(
        select(orm.NewsArticle)
        .where(
            orm.NewsArticle.tickers.contains([ticker]),
            orm.NewsArticle.tags.is_(None),
            orm.NewsArticle.published_at
            >= datetime.combine(today - timedelta(days=FIRST_DAYS), time(0), tzinfo=UTC),
        )
        .order_by(orm.NewsArticle.published_at.desc())
        .limit(MAX_TAGGED_PER_TICKER)
    ).all()
    if not rows:
        return 0
    text = "\n".join(f"[{r.id}] {r.title}" for r in rows)
    try:
        tagging = llm.extract(instructions=TAG_INSTRUCTIONS, text=text, schema=Tagging)
    except DataError as exc:
        logger.warning("news tagging failed", extra={"ticker": ticker, "error": str(exc)})
        return 0
    by_id = {i.id: i.tags for i in tagging.items}
    tagged = 0
    for row in rows:
        if row.id in by_id:
            row.tags = list(dict.fromkeys(by_id[row.id]))
            tagged += 1
    session.commit()
    return tagged
