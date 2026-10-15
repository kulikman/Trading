from datetime import UTC, date, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.errors import DataError
from adapters.massive.models import NewsArticle
from agents.news.collect import Tagging, collect_news
from core.config import load_config
from core.db import models as orm
from core.db.store import sync_universe

CONFIG = load_config()
TODAY = date(2026, 10, 15)


def article(n: int, tickers: list[str]) -> NewsArticle:
    return NewsArticle.model_validate(
        {
            "id": f"a{n}",
            "title": f"Новость {n}",
            "article_url": f"https://example.com/{n}",
            "published_utc": (datetime(2026, 10, 14, tzinfo=UTC) + timedelta(hours=n)).isoformat(),
            "tickers": tickers,
        }
    )


class Source:
    def __init__(self, fail: set[str] | None = None) -> None:
        self.calls: list[tuple[str, date | None]] = []
        self.fail = fail or set()

    def news(self, ticker: str, published_gte: date | None = None) -> list[NewsArticle]:
        self.calls.append((ticker, published_gte))
        if ticker in self.fail:
            raise DataError("massive", "HTTP 503")
        return [article(1, ["NFLX"]), article(2, ["NFLX", "DIS"])] if ticker == "NFLX" else []


class Llm:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail

    def extract[M: BaseModel](self, *, instructions: str, text: str, schema: type[M]) -> M:
        if self.fail:
            raise DataError("llm", "invalid output")
        assert schema is Tagging
        ids = [line[1 : line.index("]")] for line in text.splitlines()]
        tags = {"massive:a1": ["M&A"], "massive:a2": []}
        return schema.model_validate({"items": [{"id": i, "tags": tags[i]} for i in ids]})


def tags(session: Session) -> dict[str, list[str] | None]:
    return {
        a.id: a.tags for a in session.scalars(select(orm.NewsArticle).order_by(orm.NewsArticle.id))
    }


def test_collect_saves_once_and_tags(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    source = Source()
    first = collect_news(session, source, Llm(), ["NFLX", "TSLA"], TODAY)
    assert (first.saved, first.tagged, first.failed) == (2, 2, [])
    assert source.calls[0] == ("NFLX", TODAY - timedelta(days=30))  # первый раз — 30 дней
    assert tags(session) == {"massive:a1": ["M&A"], "massive:a2": []}
    again = collect_news(session, source, Llm(), ["NFLX"], TODAY)
    assert (again.saved, again.tagged) == (0, 0)  # без дублей, размеченное не трогается
    assert source.calls[-1] == ("NFLX", date(2026, 10, 14))  # с последней сохранённой


def test_llm_failure_leaves_tags_for_next_day(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    result = collect_news(session, Source(), Llm(fail=True), ["NFLX"], TODAY)
    assert (result.saved, result.tagged) == (2, 0)
    assert tags(session) == {"massive:a1": None, "massive:a2": None}
    assert collect_news(session, Source(), Llm(), ["NFLX"], TODAY).tagged == 2  # дозаметка


def test_source_failure_does_not_stop_others(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    result = collect_news(session, Source(fail={"TSLA"}), None, ["TSLA", "NFLX"], TODAY)
    assert (result.saved, result.failed) == (2, ["TSLA"])
