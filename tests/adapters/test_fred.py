from datetime import date

import pytest

from adapters.errors import DataError
from adapters.fred.client import VIX, FredClient, fred_api_key
from core.config import ConfigError, load_config
from core.config.sources import FredSettings
from tests.adapters.fakes import FakeApi, load_json

KEY = "fredtestkey000000000000000000000"
PATH = "/fred/series/observations"


@pytest.fixture
def settings() -> FredSettings:
    return load_config().sources.fred


def client(settings: FredSettings, fake: FakeApi) -> FredClient:
    return FredClient.create(settings, KEY, transport=fake.transport())


def test_observations_contract(settings: FredSettings) -> None:
    fake = FakeApi({PATH: lambda _: load_json("fred", "vixcls.json")})
    rows = client(settings, fake).observations(VIX, date(2026, 10, 5), date(2026, 10, 12))
    assert [r.value for r in rows] == [16.42, 17.05, 18.30, 17.61, 16.98, None]  # "." → нет данных
    params = fake.requests[0].url.params
    assert (params["series_id"], params["file_type"], params["api_key"]) == (VIX, "json", KEY)
    assert (params["observation_start"], params["observation_end"]) == ("2026-10-05", "2026-10-12")


def test_latest_skips_missing_value(settings: FredSettings) -> None:
    fake = FakeApi({PATH: lambda _: load_json("fred", "vixcls.json")})
    latest = client(settings, fake).latest(VIX, date(2026, 10, 12), lookback_days=7)
    assert (latest.date, latest.value) == (date(2026, 10, 9), 16.98)


def test_latest_without_values_is_data_error(settings: FredSettings) -> None:
    empty = {"observations": [{"date": "2026-10-12", "value": "."}]}
    with pytest.raises(DataError, match="no value in 7 days"):
        client(settings, FakeApi({PATH: lambda _: empty})).latest(VIX, date(2026, 10, 12), 7)


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"error": "x"}, "expected an observations list"),
        ({"observations": [{"value": "1"}]}, "unexpected observation"),
    ],
)
def test_bad_payload(settings: FredSettings, body: dict[str, object], message: str) -> None:
    with pytest.raises(DataError, match=message):
        client(settings, FakeApi({PATH: lambda _: body})).observations(VIX)


def test_http_error_hides_api_key(settings: FredSettings) -> None:
    fake = FakeApi({PATH: lambda _: (400, {"error_message": "Bad Request"})})
    with pytest.raises(DataError, match="HTTP 400") as exc_info:
        client(settings, fake).observations(VIX)
    assert KEY not in str(exc_info.value)
    assert "api_key=***" in str(exc_info.value)


def test_api_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRED_API_KEY", "k")
    assert fred_api_key() == "k"
    monkeypatch.delenv("FRED_API_KEY")
    with pytest.raises(ConfigError, match="FRED_API_KEY"):
        fred_api_key()


def test_numeric_value_passes_through() -> None:
    from adapters.fred.client import FredObservation

    assert FredObservation.model_validate({"date": "2026-10-12", "value": 17.5}).value == 17.5
