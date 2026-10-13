"""Модели ответов Massive. Только поля, описанные в документации massive.com/docs (13.10.2026)."""

from datetime import UTC, date, datetime
from typing import Any, Literal

from pydantic import AwareDatetime, Field, field_validator

from adapters.api_model import ApiModel
from core.domain.news import NewsItem

NANOS_PER_SECOND = 1_000_000_000
MILLIS_PER_SECOND = 1_000

ContractType = Literal["call", "put", "other"]


def _from_millis(value: Any) -> Any:
    if isinstance(value, int):
        return datetime.fromtimestamp(value / MILLIS_PER_SECOND, tz=UTC)
    return value


def _from_nanos(value: Any) -> Any:
    if isinstance(value, int):
        return datetime.fromtimestamp(value / NANOS_PER_SECOND, tz=UTC)
    return value


class Bar(ApiModel):
    """Свеча /v2/aggs: o, h, l, c, v, vw, t (Unix ms начала окна), n."""

    open: float = Field(alias="o")
    high: float = Field(alias="h")
    low: float = Field(alias="l")
    close: float = Field(alias="c")
    volume: float = Field(alias="v")
    vwap: float | None = Field(default=None, alias="vw")
    start: AwareDatetime = Field(alias="t")
    transactions: int | None = Field(default=None, alias="n")

    _start = field_validator("start", mode="before")(_from_millis)


class StockQuote(ApiModel):
    """NBBO /v2/last/nbbo: P ask, S ask size, p bid, s bid size, t — SIP-время в наносекундах."""

    ask: float = Field(alias="P")
    ask_size: float = Field(alias="S")
    bid: float = Field(alias="p")
    bid_size: float = Field(alias="s")
    sip_time: AwareDatetime = Field(alias="t")

    _sip_time = field_validator("sip_time", mode="before")(_from_nanos)


class StockSnapshot(ApiModel):
    """Снимок /v2/snapshot/.../tickers/{ticker}.

    TODO(OPEN_QUESTIONS): ключи внутри day / prevDay / lastQuote / lastTrade / min на странице
    снимка не описаны — храним как есть и не интерпретируем, пока смысл не подтверждён.
    """

    ticker: str
    updated: int | None = None
    day: dict[str, float] | None = None
    prev_day: dict[str, float] | None = Field(default=None, alias="prevDay")
    last_quote: dict[str, float] | None = Field(default=None, alias="lastQuote")
    last_trade: dict[str, Any] | None = Field(default=None, alias="lastTrade")
    todays_change: float | None = Field(default=None, alias="todaysChange")
    todays_change_perc: float | None = Field(default=None, alias="todaysChangePerc")


class OptionContract(ApiModel):
    """Справочник /v3/reference/options/contracts."""

    ticker: str
    underlying_ticker: str
    contract_type: ContractType
    exercise_style: str
    expiration_date: date
    strike_price: float
    shares_per_contract: float
    primary_exchange: str | None = None
    cfi: str | None = None


class OptionDetails(ApiModel):
    contract_type: ContractType
    exercise_style: str
    expiration_date: date
    shares_per_contract: float
    strike_price: float
    ticker: str


class Greeks(ApiModel):
    """Документация: греки могут отсутствовать, например глубоко в деньгах."""

    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None


class OptionQuote(ApiModel):
    """last_quote — только если тариф включает котировки.

    TODO(OPEN_QUESTIONS): единица last_updated явно не указана (по примеру — наносекунды).
    """

    ask: float
    bid: float
    ask_size: float | None = None
    bid_size: float | None = None
    midpoint: float | None = None
    last_updated: int | None = None
    timeframe: str | None = None


class UnderlyingAsset(ApiModel):
    """Цена базового актива — только если тариф на акции это позволяет."""

    ticker: str
    price: float | None = None
    last_updated: int | None = None
    timeframe: str | None = None


class OptionSnapshot(ApiModel):
    """Элемент /v3/snapshot/options/{underlyingAsset}."""

    details: OptionDetails
    break_even_price: float | None = None
    greeks: Greeks | None = None
    implied_volatility: float | None = None
    open_interest: float | None = None
    last_quote: OptionQuote | None = None
    underlying_asset: UnderlyingAsset | None = None


class NewsPublisher(ApiModel):
    name: str
    homepage_url: str | None = None


class NewsInsight(ApiModel):
    """Тональность новости по тикеру — оценка Massive, не наша модель."""

    ticker: str
    sentiment: str | None = None
    sentiment_reasoning: str | None = None


class NewsArticle(ApiModel):
    """Элемент /v2/reference/news. published_utc — RFC3339."""

    id: str
    title: str
    article_url: str
    published_utc: AwareDatetime
    tickers: list[str]
    author: str | None = None
    description: str | None = None
    keywords: list[str] | None = None
    publisher: NewsPublisher | None = None
    insights: list[NewsInsight] | None = None


def news_item(article: NewsArticle) -> NewsItem:
    """Статья Massive → доменная новость. Идентификатор с префиксом источника."""
    return NewsItem(
        id=f"massive:{article.id}",
        source="massive",
        published_at=article.published_utc,
        title=article.title,
        url=article.article_url,
        tickers=article.tickers,
        publisher=article.publisher.name if article.publisher else None,
        author=article.author,
        description=article.description,
        keywords=article.keywords,
        insights=[i.model_dump() for i in article.insights] if article.insights else None,
    )
