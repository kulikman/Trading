import logging
from collections.abc import Callable
from datetime import date

import pytest

from adapters.errors import DataError
from adapters.finnhub.client import FinnhubClient, finnhub_api_key
from adapters.finnhub.mapping import consensus_snapshots
from adapters.finnhub.models import FinnhubEarning, report_time_from_hour
from core.config import ConfigError, load_config
from core.config.sources import FinnhubSettings
from tests.adapters.fakes import Body, FakeApi, load_json

KEY = "finnhub-test-token"
UNIVERSE = {"GS", "MS", "NFLX", "TSLA"}


@pytest.fixture
def settings() -> FinnhubSettings:
    return load_config().sources.finnhub


def client(settings: FinnhubSettings, fake: FakeApi) -> FinnhubClient:
    return FinnhubClient.create(settings, KEY, transport=fake.transport())


def calendar_route(_: object) -> dict[str, object]:
    data = load_json("finnhub", "earnings_calendar.json")
    assert isinstance(data, dict)
    return data


@pytest.mark.parametrize(
    ("hour", "expected"),
    [("bmo", "BMO"), ("amc", "AMC"), ("dmh", "DURING"), ("AMC", "AMC"), ("", None), (None, None)],
)
def test_report_time_from_hour(hour: str | None, expected: str | None) -> None:
    assert report_time_from_hour(hour) == expected


def test_unknown_hour_is_none_with_warning(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="adapters.finnhub.models"):
        assert report_time_from_hour("pre") is None
    assert caplog.records[0].getMessage() == "unknown finnhub hour value"


def test_earnings_calendar_contract(
    settings: FinnhubSettings, caplog: pytest.LogCaptureFixture
) -> None:
    fake = FakeApi({"/api/v1/calendar/earnings": calendar_route})
    with caplog.at_level(logging.DEBUG, logger="adapters.http"):
        rows = client(settings, fake).earnings_calendar(date(2026, 10, 13), date(2026, 11, 12))
    assert [(r.symbol, r.report_time) for r in rows] == [
        ("GS", "BMO"),
        ("MS", "BMO"),
        ("NFLX", "AMC"),
        ("ZZZZ", "DURING"),
        ("TSLA", None),
    ]
    gs = rows[0]
    assert (gs.date, gs.fiscal_period, gs.eps_estimate, gs.revenue_estimate) == (
        date(2026, 10, 14),
        "2026Q3",
        11.82,
        14_100_000_000,
    )
    params = fake.requests[0].url.params
    assert (params["from"], params["to"], params["token"]) == ("2026-10-13", "2026-11-12", KEY)
    assert "symbol" not in params
    assert all(KEY not in str(record.__dict__) for record in caplog.records)


def test_earnings_history_is_a_top_level_array(settings: FinnhubSettings) -> None:
    fake = FakeApi(
        {"/api/v1/stock/earnings": lambda _: load_json("finnhub", "stock_earnings_gs.json")}
    )
    rows = client(settings, fake).earnings_history("GS", limit=4)
    assert [(r.period, r.actual, r.estimate, r.surprise_percent) for r in rows] == [
        (date(2026, 6, 30), 12.25, 10.36, 18.2432),
        (date(2026, 3, 31), 14.12, 12.35, 14.332),
    ]
    assert fake.requests[0].url.params["limit"] == "4"


@pytest.mark.parametrize(
    ("path", "body", "call", "message"),
    [
        (
            "/api/v1/calendar/earnings",
            {"earningsCalendar": "oops"},
            lambda c: c.earnings_calendar(date(2026, 10, 13), date(2026, 10, 14)),
            "earningsCalendar list",
        ),
        (
            "/api/v1/calendar/earnings",
            {"earningsCalendar": [{"symbol": "GS"}]},
            lambda c: c.earnings_calendar(date(2026, 10, 13), date(2026, 10, 14), "GS"),
            "unexpected FinnhubEarning shape",
        ),
        (
            "/api/v1/stock/earnings",
            {"error": "x"},
            lambda c: c.earnings_history("GS"),
            "JSON array",
        ),
    ],
)
def test_bad_payload_is_data_error(
    settings: FinnhubSettings,
    path: str,
    body: Body,
    call: Callable[[FinnhubClient], object],
    message: str,
) -> None:
    fake = FakeApi({path: lambda _: body})
    with pytest.raises(DataError, match=message):
        call(client(settings, fake))


def test_auth_error_never_shows_token(settings: FinnhubSettings) -> None:
    fake = FakeApi({"/api/v1/calendar/earnings": lambda _: (401, {"error": "Invalid API key"})})
    with pytest.raises(DataError, match="HTTP 401") as exc_info:
        client(settings, fake).earnings_calendar(date(2026, 10, 13), date(2026, 10, 14))
    assert KEY not in str(exc_info.value)
    assert "token=***" in str(exc_info.value)


def test_consensus_snapshots_filter_universe_and_skip_missing() -> None:
    rows = [
        FinnhubEarning.model_validate(r)
        for r in load_json("finnhub", "earnings_calendar.json")["earningsCalendar"]
    ]
    snapshots = consensus_snapshots(rows, date(2026, 10, 13), UNIVERSE)
    assert [(s.ticker, s.fiscal_period, s.eps_estimate) for s in snapshots] == [
        ("GS", "2026Q3", 11.82),
        ("MS", "2026Q3", 2.05),
        ("NFLX", "2026Q3", 5.10),
    ]  # ZZZZ — не из вселенной; TSLA — без оценок
    assert all(s.as_of == date(2026, 10, 13) for s in snapshots)


def test_consensus_snapshots_dedupe_last_wins() -> None:
    first = FinnhubEarning.model_validate(
        {"symbol": "GS", "date": "2026-10-14", "year": 2026, "quarter": 3, "epsEstimate": 1.0}
    )
    second = first.model_copy(update={"eps_estimate": 2.0})
    no_period = FinnhubEarning.model_validate(
        {"symbol": "MS", "date": "2026-10-15", "epsEstimate": 1.0}
    )
    snapshots = consensus_snapshots([first, second, no_period], date(2026, 10, 13), UNIVERSE)
    assert [(s.ticker, s.eps_estimate) for s in snapshots] == [("GS", 2.0)]


def test_api_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    assert finnhub_api_key() == "k"
    monkeypatch.delenv("FINNHUB_API_KEY")
    with pytest.raises(ConfigError, match="FINNHUB_API_KEY"):
        finnhub_api_key()
