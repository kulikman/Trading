import logging
from collections.abc import Callable
from datetime import date, timedelta

import httpx
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
        rows = client(settings, fake).earnings_calendar(date(2026, 10, 14), date(2026, 10, 20))
    assert [(r.symbol, r.report_time) for r in rows] == [
        ("BAC", "BMO"),
        ("MS", "BMO"),
        ("NFLX", "AMC"),
        ("TSLA", "AMC"),
        ("ADC", "AMC"),
        ("ADX", None),
    ]
    bac = rows[0]
    assert (bac.date, bac.fiscal_period, bac.eps_estimate, bac.revenue_estimate) == (
        date(2026, 10, 14),
        "2026Q3",
        1.1619,
        31_315_190_571,
    )
    assert rows[-1].eps_estimate is None
    [request] = fake.requests  # окно в пределах одного куска — один запрос
    params = request.url.params
    assert (params["from"], params["to"], params["token"]) == ("2026-10-14", "2026-10-20", KEY)
    assert "symbol" not in params
    assert all(KEY not in str(record.__dict__) for record in caplog.records)


def test_earnings_history_is_a_top_level_array(settings: FinnhubSettings) -> None:
    fake = FakeApi(
        {"/api/v1/stock/earnings": lambda _: load_json("finnhub", "stock_earnings_gs.json")}
    )
    rows = client(settings, fake).earnings_history("GS", limit=4)
    assert [(r.period, r.actual, r.estimate, r.surprise_percent) for r in rows] == [
        (date(2026, 9, 30), 17.01, 15.0539, 12.994),
        (date(2026, 6, 30), 20.98, 14.9103, 40.7081),
        (date(2026, 3, 31), 17.55, 16.9874, 3.3119),
        (date(2025, 12, 31), 14.01, 12.0225, 16.5315),
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
        ("MS", "2026Q3", 3.1669),
        ("NFLX", "2026Q3", 0.8385),
        ("TSLA", "2026Q3", 0.4343),
    ]  # BAC, ADC, ADX — не из вселенной теста
    assert all(s.as_of == date(2026, 10, 13) for s in snapshots)


def test_consensus_snapshots_dedupe_last_wins() -> None:
    first = FinnhubEarning.model_validate(
        {"symbol": "GS", "date": "2026-10-14", "year": 2026, "quarter": 3, "epsEstimate": 1.0}
    )
    second = first.model_copy(update={"eps_estimate": 2.0})
    no_period = FinnhubEarning.model_validate(
        {"symbol": "MS", "date": "2026-10-15", "epsEstimate": 1.0}
    )
    no_estimate = FinnhubEarning.model_validate(
        {"symbol": "NFLX", "date": "2026-10-20", "year": 2026, "quarter": 3}
    )
    snapshots = consensus_snapshots(
        [first, second, no_period, no_estimate], date(2026, 10, 13), UNIVERSE
    )
    assert [(s.ticker, s.eps_estimate) for s in snapshots] == [("GS", 2.0)]


def test_api_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FINNHUB_API_KEY", "k")
    assert finnhub_api_key() == "k"
    monkeypatch.delenv("FINNHUB_API_KEY")
    with pytest.raises(ConfigError, match="FINNHUB_API_KEY"):
        finnhub_api_key()


def one_row_per_day(per_day: int) -> Callable[[httpx.Request], dict[str, object]]:
    """Маршрут календаря: per_day строк на каждый день запрошенного окна."""

    def route(request: httpx.Request) -> dict[str, object]:
        start = date.fromisoformat(request.url.params["from"])
        end = date.fromisoformat(request.url.params["to"])
        days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        rows = [{"symbol": f"T{n}", "date": d.isoformat()} for d in days for n in range(per_day)]
        return {"earningsCalendar": rows}

    return route


def windows(fake: FakeApi) -> list[tuple[str, str]]:
    return [(r.url.params["from"], r.url.params["to"]) for r in fake.requests]


def test_calendar_window_is_requested_in_chunks(settings: FinnhubSettings) -> None:
    fake = FakeApi({"/api/v1/calendar/earnings": one_row_per_day(1)})
    rows = client(settings, fake).earnings_calendar(date(2026, 10, 14), date(2026, 11, 4))
    assert windows(fake) == [
        ("2026-10-14", "2026-10-20"),
        ("2026-10-21", "2026-10-27"),
        ("2026-10-28", "2026-11-03"),
        ("2026-11-04", "2026-11-04"),
    ]
    assert len(rows) == 22  # каждый день окна — без потерь и повторов


def test_chunk_at_row_cap_is_split_until_complete(settings: FinnhubSettings) -> None:
    capped = settings.model_copy(update={"calendar_row_cap": 5})
    fake = FakeApi({"/api/v1/calendar/earnings": one_row_per_day(2)})
    rows = client(capped, fake).earnings_calendar(date(2026, 10, 14), date(2026, 10, 20))
    assert len(rows) == 14
    assert [r.date for r in rows] == sorted(r.date for r in rows)
    assert windows(fake)[:3] == [
        ("2026-10-14", "2026-10-20"),  # 14 строк — предел, делим
        ("2026-10-14", "2026-10-17"),  # 8 — снова предел
        ("2026-10-14", "2026-10-15"),  # 4 — ниже предела
    ]


def test_single_day_at_row_cap_is_data_error(settings: FinnhubSettings) -> None:
    capped = settings.model_copy(update={"calendar_row_cap": 3})
    fake = FakeApi({"/api/v1/calendar/earnings": one_row_per_day(3)})
    with pytest.raises(DataError, match="2026-10-14 hit the 3-row cap"):
        client(capped, fake).earnings_calendar(date(2026, 10, 14), date(2026, 10, 15))
