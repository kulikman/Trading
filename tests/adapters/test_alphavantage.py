from datetime import date

import httpx
import pytest
from pydantic import ValidationError

from adapters.alphavantage.client import AlphaVantageClient, alphavantage_api_key
from adapters.alphavantage.models import report_time_from_time_of_day
from adapters.cache import MemoryCache
from adapters.errors import DataError
from core.config import ConfigError, load_config
from core.config.sources import AlphaVantageSettings
from tests.adapters.fakes import Body, FakeApi, load_json, load_text

KEY = "av-test-key"


@pytest.fixture
def settings() -> AlphaVantageSettings:
    return load_config().sources.alphavantage


def client(
    settings: AlphaVantageSettings, fake: FakeApi, cache: MemoryCache | None = None
) -> AlphaVantageClient:
    return AlphaVantageClient.create(settings, KEY, cache=cache, transport=fake.transport())


def by_function(responses: dict[str, Body]) -> FakeApi:
    return FakeApi({"/query": lambda r: responses[r.url.params["function"]]})


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("pre-market", "BMO"),
        ("post-market", "AMC"),
        ("Post-Market", "AMC"),
        ("", None),
        (None, None),
    ],
)
def test_report_time_from_time_of_day(value: str | None, expected: str | None) -> None:
    assert report_time_from_time_of_day(value) == expected


def test_earnings_calendar_recorded(settings: AlphaVantageSettings) -> None:
    fake = by_function({"EARNINGS_CALENDAR": load_text("alphavantage", "earnings_calendar.csv")})
    rows = client(settings, fake).earnings_calendar()
    by_symbol = {r.symbol: r for r in rows}
    assert len(rows) == 14
    assert by_symbol["GS"].report_time == "BMO"
    assert by_symbol["NFLX"].report_time == "AMC"
    assert by_symbol["ARTW"].report_time is None  # время пустое у большинства строк календаря
    assert by_symbol["ARTW"].estimate is None
    assert isinstance(by_symbol["GS"].report_date, date)
    params = fake.requests[0].url.params
    assert (params["function"], params["horizon"], params["apikey"]) == (
        "EARNINGS_CALENDAR",
        settings.calendar_horizon,
        KEY,
    )


def test_calendar_notice_row_is_data_error_and_not_cached(settings: AlphaVantageSettings) -> None:
    fake = by_function(
        {"EARNINGS_CALENDAR": load_text("alphavantage", "earnings_calendar_information.csv")}
    )
    av = client(settings, fake, cache=MemoryCache())
    for _ in range(2):
        with pytest.raises(DataError, match="unexpected AvCalendarRow shape"):
            av.earnings_calendar("IBM")
    assert len(fake.requests) == 2  # заглушка не закэширована


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ('{"Information": "rate limit"}', "notice instead of CSV"),
        ("a,b,c\n1,2,3\n", "unexpected calendar header"),
    ],
)
def test_calendar_other_bad_bodies(settings: AlphaVantageSettings, body: str, message: str) -> None:
    with pytest.raises(DataError, match=message):
        client(settings, by_function({"EARNINGS_CALENDAR": body})).earnings_calendar()


def test_earnings_estimates_recorded(settings: AlphaVantageSettings) -> None:
    fake = by_function(
        {"EARNINGS_ESTIMATES": load_json("alphavantage", "earnings_estimates_ibm.json")}
    )
    estimates = client(settings, fake).earnings_estimates("IBM")
    assert len(estimates) == 8
    year = estimates[0]
    assert (year.date, year.horizon) == (date(2027, 12, 31), "fiscal year")
    assert year.eps_estimate_average == 13.1512
    assert (year.eps_estimate_high, year.eps_estimate_low) == (13.86, 12.3018)
    assert year.eps_estimate_analyst_count == 23
    assert year.eps_estimate_average_90_days_ago == 13.4736
    assert year.eps_estimate_revision_down_trailing_7_days is None  # null в ответе
    assert {e.horizon for e in estimates} == {"fiscal year", "fiscal quarter"}


def test_earnings_history_recorded(settings: AlphaVantageSettings) -> None:
    fake = by_function({"EARNINGS": load_json("alphavantage", "earnings_ibm.json")})
    history = client(settings, fake).earnings("IBM")
    assert history.symbol == "IBM"
    assert len(history.quarterly) == 8
    latest = history.quarterly[0]
    assert (latest.fiscal_date_ending, latest.reported_date) == (
        date(2026, 6, 30),
        date(2026, 7, 22),
    )
    assert (latest.reported_eps, latest.estimated_eps, latest.surprise) == (2.93, 2.93, 0)
    assert latest.report_time == "AMC"


@pytest.mark.parametrize("function", ["EARNINGS_ESTIMATES", "EARNINGS"])
def test_information_notice_is_data_error_and_not_cached(
    settings: AlphaVantageSettings, function: str
) -> None:
    fake = by_function({function: load_json("alphavantage", "information.json")})
    av = client(no_backoff(settings), fake, cache=MemoryCache())
    call = av.earnings_estimates if function == "EARNINGS_ESTIMATES" else av.earnings
    for _ in range(2):
        with pytest.raises(DataError, match="Information") as exc_info:
            call("GS")
        assert KEY not in str(exc_info.value)
    # лимит повторяется max_attempts раз за вызов; второй вызов снова в сеть — не кэшировано
    assert len(fake.requests) == 2 * settings.max_attempts


def test_estimates_without_list_is_data_error(settings: AlphaVantageSettings) -> None:
    fake = by_function({"EARNINGS_ESTIMATES": {"symbol": "GS"}})
    with pytest.raises(DataError, match="expected an estimates list"):
        client(settings, fake).earnings_estimates("GS")


def no_backoff(settings: AlphaVantageSettings) -> AlphaVantageSettings:
    return settings.model_copy(update={"backoff_base_seconds": 0})


def test_http_error_never_shows_api_key(settings: AlphaVantageSettings) -> None:
    fake = FakeApi({"/query": lambda _: (500, "boom")})
    with pytest.raises(DataError, match="HTTP 500") as exc_info:
        client(no_backoff(settings), fake).earnings("GS")
    assert KEY not in str(exc_info.value)
    assert "apikey=***" in str(exc_info.value)


def test_network_failure_reports_without_key(settings: AlphaVantageSettings) -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down")

    av = AlphaVantageClient.create(no_backoff(settings), KEY, transport=httpx.MockTransport(broken))
    with pytest.raises(DataError, match="ConnectError") as exc_info:
        av.earnings("GS")
    assert KEY not in str(exc_info.value)


def test_api_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "k")
    assert alphavantage_api_key() == "k"
    monkeypatch.delenv("ALPHAVANTAGE_API_KEY")
    with pytest.raises(ConfigError, match="ALPHAVANTAGE_API_KEY"):
        alphavantage_api_key()


def test_blank_values_become_none_and_non_dict_input_passes_through() -> None:
    from adapters.alphavantage.models import AvQuarterlyEarning

    row = AvQuarterlyEarning.model_validate(
        {
            "fiscalDateEnding": "2026-06-30",
            "reportedEPS": "None",
            "estimatedEPS": "",
            "surprise": "-",
        }
    )
    assert (row.reported_eps, row.estimated_eps, row.surprise) == (None, None, None)
    with pytest.raises(ValidationError):
        AvQuarterlyEarning.model_validate(["not", "a", "dict"])  # не словарь — до pydantic как есть


def test_rate_limit_notice_quoting_the_key_is_redacted(settings: AlphaVantageSettings) -> None:
    # Настоящий текст заглушки (14.10.2026) цитирует ключ — в DataError и лог он попасть не должен.
    notice = {
        "Information": f"We have detected your API key as {KEY} and our standard API rate limit "
        "is 25 requests per day."
    }
    fake = by_function({"EARNINGS": notice})
    with pytest.raises(DataError) as exc_info:
        client(settings, fake).earnings("IBM")
    assert KEY not in str(exc_info.value)
    assert "API key as ***" in exc_info.value.detail
    assert exc_info.value.__cause__ is None  # исходное сообщение с ключом не сцеплено
