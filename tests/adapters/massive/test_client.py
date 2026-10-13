from datetime import UTC, date, datetime
from typing import Any

import httpx
import pytest

from adapters.errors import DataError
from adapters.massive.client import massive_api_key
from adapters.massive.models import Bar, StockQuote
from core.config import ConfigError
from core.config.sources import MassiveSettings
from tests.adapters.massive.conftest import API_KEY, FakeMassive, fixture, make_client

AGGS_PATH = "/v2/aggs/ticker/GS/range/1/day/2026-10-08/2026-10-12"
CHAIN_PATH = "/v3/snapshot/options/GS"


def _aggs(request: httpx.Request) -> dict[str, Any]:
    return fixture("aggs_gs_page2" if "cursor" in request.url.params else "aggs_gs_page1")


def test_aggregates_follow_next_url_and_parse_bars(settings: MassiveSettings) -> None:
    fake = FakeMassive({AGGS_PATH: _aggs})
    bars = make_client(settings, fake).aggregates(
        "GS", 1, "day", date(2026, 10, 8), date(2026, 10, 12)
    )
    assert [bar.close for bar in bars] == [888.4, 893.2, 897.0]
    assert bars[0].start == datetime(2026, 10, 8, 4, 0, tzinfo=UTC)  # полночь ET в UTC
    first, second = fake.requests
    assert first.url.params["sort"] == "asc"
    assert first.url.params["adjusted"] == "true"
    assert first.url.params["limit"] == str(settings.page_limit.aggregates)
    assert second.url.params["cursor"] == "bGltaXQ9Mg"
    assert "sort" not in second.url.params  # курсор несёт параметры сам
    assert all(r.headers["Authorization"] == f"Bearer {API_KEY}" for r in fake.requests)
    assert all(API_KEY not in str(r.url) for r in fake.requests)


def test_last_quote(settings: MassiveSettings) -> None:
    fake = FakeMassive({"/v2/last/nbbo/GS": lambda _: fixture("last_nbbo_gs")})
    quote = make_client(settings, fake).last_quote("GS")
    assert (quote.bid, quote.ask, quote.bid_size, quote.ask_size) == (896.98, 897.12, 2, 3)
    assert quote.sip_time == datetime(2026, 10, 12, 19, 59, 58, tzinfo=UTC)


def test_snapshot_recorded_keeps_undocumented_keys_raw(settings: MassiveSettings) -> None:
    fake = FakeMassive(
        {"/v2/snapshot/locale/us/markets/stocks/tickers/GS": lambda _: fixture("snapshot_gs")}
    )
    snapshot = make_client(settings, fake).snapshot("GS")
    assert snapshot.ticker == "GS"
    assert snapshot.prev_day is not None
    assert snapshot.prev_day["c"] == 893.95
    assert snapshot.day is not None
    assert snapshot.day["dv"] == 3672378.765755  # в живом ответе это строка
    assert snapshot.last_quote is None  # тариф без котировок
    assert snapshot.last_trade is None  # и без сделок


def test_aggregates_recorded_response(settings: MassiveSettings) -> None:
    path = "/v2/aggs/ticker/GS/range/1/day/2026-10-01/2026-10-12"
    fake = FakeMassive({path: lambda _: fixture("aggs_gs_recorded")})
    bars = make_client(settings, fake).aggregates(
        "GS", 1, "day", date(2026, 10, 1), date(2026, 10, 12)
    )
    assert len(bars) == 8
    assert bars[0].start == datetime(2026, 10, 1, 4, 0, tzinfo=UTC)  # полночь ET
    assert (bars[-1].start.date(), bars[-1].close) == (date(2026, 10, 12), 893.95)


def test_option_contracts_recorded_send_filters(settings: MassiveSettings) -> None:
    def contracts_route(request: httpx.Request) -> dict[str, Any]:
        if "cursor" in request.url.params:
            return {"status": "OK", "results": []}
        return fixture("options_contracts_gs")

    fake = FakeMassive({"/v3/reference/options/contracts": contracts_route})
    contracts = make_client(settings, fake).option_contracts(
        "GS",
        contract_type="call",
        expiration_gte=date(2026, 10, 13),
        expiration_lte=date(2026, 10, 30),
    )
    assert len(contracts) == 5
    assert [c.strike_price for c in contracts] == [410, 420, 430, 440, 450]
    assert {(c.contract_type, c.expiration_date) for c in contracts} == {
        ("call", date(2026, 10, 16))
    }
    assert len(fake.requests) == 2  # вторая страница — по next_url
    params = fake.requests[0].url.params
    assert params["underlying_ticker"] == "GS"
    assert params["contract_type"] == "call"
    assert params["expiration_date.gte"] == "2026-10-13"
    assert params["expiration_date.lte"] == "2026-10-30"
    assert params["expired"] == "false"
    assert "as_of" not in params


def test_option_chain_parses_iv_greeks_oi_quotes(settings: MassiveSettings) -> None:
    fake = FakeMassive({CHAIN_PATH: lambda _: fixture("option_chain_gs")})
    chain = make_client(settings, fake).option_chain("GS", strike_gte=890, strike_lte=910)
    assert len(chain) == 8
    call = chain[2]
    assert (call.details.contract_type, call.details.strike_price) == ("call", 900)
    assert call.implied_volatility == 0.60
    assert call.greeks is not None
    assert call.greeks.delta == 0.49
    assert call.open_interest == 1543
    assert call.last_quote is not None
    assert call.last_quote.midpoint == 20.0
    assert call.underlying_asset is not None
    assert call.underlying_asset.price == 897.0
    assert fake.requests[0].url.params["strike_price.gte"] == "890"


def test_too_many_pages_is_data_error(settings: MassiveSettings) -> None:
    def endless(request: httpx.Request) -> dict[str, Any]:
        return {
            "status": "OK",
            "results": [],
            "next_url": f"https://api.massive.com{CHAIN_PATH}?cursor=x",
        }

    fake = FakeMassive({CHAIN_PATH: endless})
    with pytest.raises(DataError, match="more than"):
        make_client(settings, fake).option_chain("GS")
    assert len(fake.requests) == settings.max_pages


@pytest.mark.parametrize(
    ("route", "payload", "call", "message"),
    [
        (
            CHAIN_PATH,
            {"status": "OK", "results": [{"open_interest": 1}]},
            lambda c: c.option_chain("GS"),
            "unexpected OptionSnapshot shape",
        ),
        (
            CHAIN_PATH,
            {"status": "OK", "results": {"oops": 1}},
            lambda c: c.option_chain("GS"),
            "expected a results list",
        ),
        ("/v2/last/nbbo/GS", {"status": "OK"}, lambda c: c.last_quote("GS"), "no StockQuote data"),
    ],
)
def test_unexpected_payload_is_data_error(
    settings: MassiveSettings, route: str, payload: dict[str, Any], call: Any, message: str
) -> None:
    fake = FakeMassive({route: lambda _: payload})
    with pytest.raises(DataError, match=message):
        call(make_client(settings, fake))


def test_api_key_comes_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASSIVE_API_KEY", "from-env")
    assert massive_api_key() == "from-env"
    monkeypatch.delenv("MASSIVE_API_KEY")
    with pytest.raises(ConfigError, match="MASSIVE_API_KEY"):
        massive_api_key()


def test_exactly_max_pages_is_not_an_error(settings: MassiveSettings) -> None:
    calls = {"n": 0}

    def pages(request: httpx.Request) -> dict[str, Any]:
        calls["n"] += 1
        has_more = calls["n"] < settings.max_pages
        page: dict[str, Any] = {
            "status": "OK",
            "results": [fixture("option_chain_gs")["results"][0]],
        }
        if has_more:
            page["next_url"] = f"https://api.massive.com{CHAIN_PATH}?cursor={calls['n']}"
        return page

    chain = make_client(settings, FakeMassive({CHAIN_PATH: pages})).option_chain("GS")
    assert len(chain) == settings.max_pages


def test_timestamps_accept_iso_strings() -> None:
    bar = Bar.model_validate(
        {"o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10, "t": "2026-10-12T04:00:00Z"}
    )
    quote = StockQuote.model_validate({"P": 2, "S": 1, "p": 1, "s": 1, "t": "2026-10-12T19:59:58Z"})
    assert bar.start == datetime(2026, 10, 12, 4, 0, tzinfo=UTC)
    assert quote.sip_time == datetime(2026, 10, 12, 19, 59, 58, tzinfo=UTC)


def test_plan_without_entitlement_is_data_error(settings: MassiveSettings) -> None:
    fake = FakeMassive({CHAIN_PATH: lambda _: (403, fixture("not_entitled"))})
    with pytest.raises(DataError, match=r"HTTP 403.*not entitled") as exc_info:
        make_client(settings, fake).option_chain("GS")
    assert exc_info.value.source == "massive"
    assert len(fake.requests) == 1  # 403 не повторяется
