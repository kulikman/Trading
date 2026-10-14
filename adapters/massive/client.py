"""Клиент Massive REST: свечи, котировки, снимки, опционные контракты и цепочки (SPEC §6)."""

import time
from collections.abc import Callable
from datetime import date
from typing import Any, Literal

import httpx
from pydantic import ValidationError

from adapters.api_model import ApiModel, require_env
from adapters.cache import Cache
from adapters.errors import DataError
from adapters.http import JsonHttpClient, Params, RateLimiter, RetryPolicy
from adapters.massive.models import (
    Bar,
    ContractType,
    NewsArticle,
    OptionContract,
    OptionSnapshot,
    StockQuote,
    StockSnapshot,
    TickerChange,
)
from core.config.sources import MassiveSettings

SOURCE = "massive"
Timespan = Literal["second", "minute", "hour", "day", "week", "month", "quarter", "year"]


def massive_api_key() -> str:
    """MASSIVE_API_KEY из окружения. В логи и LLM ключ не передаётся."""
    return require_env("MASSIVE_API_KEY")


class MassiveClient:
    def __init__(self, http: JsonHttpClient, settings: MassiveSettings) -> None:
        self._http = http
        self._settings = settings

    @classmethod
    def create(
        cls,
        settings: MassiveSettings,
        api_key: str,
        cache: Cache | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> "MassiveClient":
        """Клиент с ключом в заголовке Authorization: Bearer (не в URL — не попадёт в лог)."""
        http = JsonHttpClient(
            source=SOURCE,
            base_url=settings.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout_seconds=settings.timeout_seconds,
            retry=RetryPolicy(settings.max_attempts, settings.backoff_base_seconds),
            cache=cache,
            transport=transport,
        )
        return cls(http, settings)

    @classmethod
    def create_history(
        cls,
        settings: MassiveSettings,
        api_key: str,
        cache: Cache | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> "MassiveClient":
        """Клиент исторических опционов: лимит history.requests_per_minute, долгие паузы при 429."""
        history = settings.history
        http = JsonHttpClient(
            source=SOURCE,
            base_url=settings.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout_seconds=settings.timeout_seconds,
            retry=RetryPolicy(history.max_attempts, history.backoff_base_seconds),
            cache=cache,
            transport=transport,
            sleep=sleep,
            throttle=RateLimiter(history.requests_per_minute, 60, clock=clock, sleep=sleep),
        )
        return cls(http, settings)

    def aggregates(
        self,
        ticker: str,
        multiplier: int,
        timespan: Timespan,
        start: date,
        end: date,
        *,
        adjusted: bool = True,
    ) -> list[Bar]:
        """Свечи за период, от старых к новым."""
        path = f"/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{start}/{end}"
        params: Params = {
            "adjusted": adjusted,
            "sort": "asc",
            "limit": self._settings.page_limit.aggregates,
        }
        rows = self._paginate(path, params, self._settings.cache_ttl_seconds.aggregates)
        return [_parse(Bar, row) for row in rows]

    def last_quote(self, ticker: str) -> StockQuote:
        """Последняя NBBO-котировка. По документации — только тарифы Stocks Advanced и выше."""
        payload = self._http.get_json(
            f"/v2/last/nbbo/{ticker}", ttl_seconds=self._settings.cache_ttl_seconds.last_quote
        )
        return _parse(StockQuote, payload.get("results"))

    def snapshot(self, ticker: str) -> StockSnapshot:
        """Снимок акции. Тарифы Stocks Starter и выше."""
        payload = self._http.get_json(
            f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker}",
            ttl_seconds=self._settings.cache_ttl_seconds.snapshot,
        )
        return _parse(StockSnapshot, payload.get("ticker"))

    def option_contracts(
        self,
        underlying: str,
        *,
        contract_type: ContractType | None = None,
        expiration_gte: date | None = None,
        expiration_lte: date | None = None,
        as_of: date | None = None,
        expired: bool = False,
        strike_gte: float | None = None,
        strike_lte: float | None = None,
    ) -> list[OptionContract]:
        """Справочник контрактов по базовому активу. expired=True — только истёкшие."""
        params = _drop_none(
            {
                "underlying_ticker": underlying,
                "contract_type": contract_type,
                "expiration_date.gte": expiration_gte,
                "expiration_date.lte": expiration_lte,
                "strike_price.gte": strike_gte,
                "strike_price.lte": strike_lte,
                "as_of": as_of,
                "expired": expired,
                "limit": self._settings.page_limit.option_contracts,
            }
        )
        rows = self._paginate(
            "/v3/reference/options/contracts",
            params,
            self._settings.cache_ttl_seconds.option_contracts,
        )
        return [_parse(OptionContract, row) for row in rows]

    def option_chain(
        self,
        underlying: str,
        *,
        contract_type: ContractType | None = None,
        expiration_gte: date | None = None,
        expiration_lte: date | None = None,
        strike_gte: float | None = None,
        strike_lte: float | None = None,
    ) -> list[OptionSnapshot]:
        """Снимок цепочки: IV, греки, OI; котировки и цена базового актива — по тарифу."""
        params = _drop_none(
            {
                "contract_type": contract_type,
                "expiration_date.gte": expiration_gte,
                "expiration_date.lte": expiration_lte,
                "strike_price.gte": strike_gte,
                "strike_price.lte": strike_lte,
                "limit": self._settings.page_limit.option_chain,
            }
        )
        rows = self._paginate(
            f"/v3/snapshot/options/{underlying}",
            params,
            self._settings.cache_ttl_seconds.option_chain,
        )
        return [_parse(OptionSnapshot, row) for row in rows]

    def ticker_changes(self, ticker: str) -> list[TickerChange]:
        """История тикеров бумаги по возрастанию даты (переименования, например FB → META)."""
        payload = self._http.get_json(
            f"/vX/reference/tickers/{ticker}/events",
            ttl_seconds=self._settings.cache_ttl_seconds.ticker_events,
        )
        results = payload.get("results")
        if not isinstance(results, dict):
            raise DataError(SOURCE, f"{ticker}: no results in ticker events")
        events = results.get("events", [])
        if not isinstance(events, list):
            raise DataError(SOURCE, f"{ticker}: ticker events is not a list")
        changes = [
            _parse(
                TickerChange,
                {"date": e.get("date"), "ticker": (e.get("ticker_change") or {}).get("ticker")},
            )
            for e in events
            if isinstance(e, dict) and e.get("type") == "ticker_change"
        ]
        return sorted(changes, key=lambda c: c.date)

    def news(self, ticker: str, published_gte: date | None = None) -> list[NewsArticle]:
        """Новости по тикеру, от новых к старым. Входит во все тарифы Stocks."""
        params = _drop_none(
            {
                "ticker": ticker,
                "published_utc.gte": published_gte,
                "order": "desc",
                "sort": "published_utc",
                "limit": self._settings.page_limit.news,
            }
        )
        rows = self._paginate("/v2/reference/news", params, self._settings.cache_ttl_seconds.news)
        return [_parse(NewsArticle, row) for row in rows]

    def _paginate(self, path: str, params: Params, ttl_seconds: int) -> list[Any]:
        rows: list[Any] = []
        url = path
        page_params: Params | None = params
        for _ in range(self._settings.max_pages):
            payload = self._http.get_json(url, page_params, ttl_seconds)
            results = payload.get("results", [])
            if not isinstance(results, list):
                raise DataError(SOURCE, f"expected a results list from {path}")
            rows.extend(results)
            next_url = payload.get("next_url")
            if not isinstance(next_url, str) or not next_url:
                return rows
            url = next_url
            page_params = None  # курсор уже внутри next_url
        raise DataError(SOURCE, f"more than {self._settings.max_pages} pages from {path}")


def _drop_none(params: dict[str, str | int | float | bool | date | None]) -> Params:
    return {
        k: (v.isoformat() if isinstance(v, date) else v) for k, v in params.items() if v is not None
    }


def _parse[M: ApiModel](model: type[M], data: object) -> M:
    if data is None:
        raise DataError(SOURCE, f"no {model.__name__} data in response")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise DataError(
            SOURCE, f"unexpected {model.__name__} shape: {exc.error_count()} error(s)"
        ) from exc
