from datetime import UTC, date, datetime
from typing import Any

import httpx

from adapters.massive.models import NewsArticle, news_item
from core.config.sources import MassiveSettings
from tests.adapters.massive.conftest import FakeMassive, fixture, make_client

NEWS_PATH = "/v2/reference/news"


def news_route(request: httpx.Request) -> dict[str, Any]:
    if "cursor" in request.url.params:
        return {"status": "OK", "results": []}
    return fixture("news_gs")


def test_news_recorded_response(settings: MassiveSettings) -> None:
    fake = FakeMassive({NEWS_PATH: news_route})
    articles = make_client(settings, fake).news("GS", published_gte=date(2026, 10, 1))
    assert len(articles) == 3
    first = articles[0]
    assert "GS" in first.tickers
    assert first.published_utc.tzinfo is not None
    assert first.publisher is not None
    params = fake.requests[0].url.params
    assert (params["ticker"], params["order"], params["sort"]) == ("GS", "desc", "published_utc")
    assert params["published_utc.gte"] == "2026-10-01"
    assert params["limit"] == str(settings.page_limit.news)
    assert len(fake.requests) == 2  # вторая страница — по next_url из записанного ответа


def test_news_item_mapping() -> None:
    article = NewsArticle.model_validate(fixture("news_gs")["results"][0])
    item = news_item(article)
    assert item.id == f"massive:{article.id}"
    assert (item.source, item.title, item.url) == ("massive", article.title, article.article_url)
    assert item.published_at == article.published_utc
    assert item.insights is not None
    assert item.insights[0]["ticker"] == "GS"
    assert item.tags is None


def test_news_item_without_optional_fields() -> None:
    article = NewsArticle.model_validate(
        {
            "id": "x1",
            "title": "t",
            "article_url": "https://example.com/a",
            "published_utc": "2026-10-13T12:00:00Z",
            "tickers": ["GS"],
        }
    )
    item = news_item(article)
    assert (item.publisher, item.insights) == (None, None)
    assert item.published_at == datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
