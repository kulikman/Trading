from datetime import date, datetime, time, timedelta
from typing import Any

import httpx
import pytest

from adapters.errors import DataError
from adapters.massive.client import MassiveClient
from adapters.massive.history import (
    EventDays,
    fetch_event_bars,
    option_bars,
    spot_on,
    stock_closes,
    straddle_from_bars,
)
from adapters.massive.models import Bar, OptionContract
from core.config import load_config
from core.config.sources import MassiveHistory, MassiveSettings
from core.session_guard import ET
from tests.adapters.massive.conftest import API_KEY, FakeMassive, fixture

NFLX = EventDays.of(date(2024, 10, 17), "AMC")  # записанный живой отчёт 14.10.2026
NFLX_SPOT = 687.65  # закрытие 17.10.2024 без поправки на сплит
HISTORY: MassiveHistory = load_config().sources.massive.history


def contract(kind: str, strike: float, expiration: date = date(2024, 10, 18)) -> OptionContract:
    letter = "C" if kind == "call" else "P"
    return OptionContract.model_validate(
        {
            "ticker": f"O:NFLX{expiration:%y%m%d}{letter}{int(strike * 1000):08d}",
            "underlying_ticker": "NFLX",
            "contract_type": kind,
            "exercise_style": "american",
            "expiration_date": expiration.isoformat(),
            "strike_price": strike,
            "shares_per_contract": 100,
        }
    )


def bar(day: date, close: float, volume: float = 10) -> Bar:
    start = datetime.combine(day, time(0), tzinfo=ET)
    return Bar.model_validate(
        {"o": close, "h": close, "l": close, "c": close, "v": volume, "t": start.timestamp() * 1000}
    )


class FakeSource:
    def __init__(self, contracts: list[OptionContract], bars: dict[str, list[Bar]]) -> None:
        self.contracts = contracts
        self.bars = bars
        self.contract_calls: list[dict[str, Any]] = []
        self.aggregate_calls: list[str] = []

    def option_contracts(self, underlying: str, **kwargs: Any) -> list[OptionContract]:
        self.contract_calls.append({"underlying": underlying, **kwargs})
        return self.contracts

    def aggregates(self, ticker: str, *args: Any, **kwargs: Any) -> list[Bar]:
        self.aggregate_calls.append(ticker)
        return self.bars.get(ticker, [])


def history_client(
    settings: MassiveSettings, fake: FakeMassive, sleeps: list[float]
) -> MassiveClient:
    return MassiveClient.create_history(
        settings,
        API_KEY,
        transport=httpx.MockTransport(fake),
        sleep=sleeps.append,
        clock=lambda: 0.0,
    )


@pytest.mark.parametrize(
    ("report", "time_of_day", "reaction", "pre"),
    [
        (date(2026, 10, 20), "BMO", date(2026, 10, 20), date(2026, 10, 19)),
        (date(2026, 10, 15), "AMC", date(2026, 10, 16), date(2026, 10, 15)),
        (date(2026, 10, 19), "BMO", date(2026, 10, 19), date(2026, 10, 16)),  # понедельник
        (date(2026, 10, 20), None, date(2026, 10, 20), date(2026, 10, 19)),  # как BMO
    ],
)
def test_event_days(report: date, time_of_day: Any, reaction: date, pre: date) -> None:
    days = EventDays.of(report, time_of_day)
    assert (days.reaction, days.pre) == (reaction, pre)


def test_recorded_nflx_report_end_to_end(settings: MassiveSettings) -> None:
    contracts_path = "/v3/reference/options/contracts"
    call_path = "/v2/aggs/ticker/O:NFLX241018C00687500/range/1/day/2024-10-10/2024-10-19"
    put_path = "/v2/aggs/ticker/O:NFLX241018P00687500/range/1/day/2024-10-10/2024-10-19"
    fake = FakeMassive(
        {
            contracts_path: lambda _: fixture("history_contracts_nflx"),
            call_path: lambda _: fixture("history_aggs_nflx241018c00687500"),
            put_path: lambda _: fixture("history_aggs_nflx241018p00687500"),
        }
    )
    sleeps: list[float] = []
    bars = fetch_event_bars(
        history_client(settings, fake, sleeps), "NFLX", NFLX, NFLX_SPOT, settings.history
    )
    assert [r.url.path for r in fake.requests] == [contracts_path, call_path, put_path]
    params = fake.requests[0].url.params
    assert (params["as_of"], params["expired"]) == ("2024-10-17", "false")
    assert (params["expiration_date.gte"], params["expiration_date.lte"]) == (
        "2024-10-18",
        "2024-11-01",
    )
    assert float(params["strike_price.gte"]) == pytest.approx(NFLX_SPOT * 0.85)
    assert float(params["strike_price.lte"]) == pytest.approx(NFLX_SPOT * 1.15)
    assert len(bars) == 10
    assert sleeps == []

    straddle = straddle_from_bars("NFLX", NFLX, NFLX_SPOT, bars, settings.history.risk_free_rate)
    assert (straddle.expiration, straddle.strike) == (date(2024, 10, 18), 687.5)
    assert (straddle.call_close, straddle.put_close) == (25.57, 25.27)
    assert (straddle.call_volume, straddle.put_volume) == (381, 683)
    assert straddle.move == pytest.approx(50.84 / 687.65)  # 7,39%, сверено вручную
    assert straddle.method == "close_based"
    assert straddle.call_iv is not None
    assert straddle.put_iv is not None
    # один торговый день до экспирации: σ ≈ move / (0,8 · √T) ≈ 1,7
    assert 1.2 < straddle.call_iv < 2.5
    assert 1.2 < straddle.put_iv < 2.5


def test_history_client_respects_requests_per_minute(settings: MassiveSettings) -> None:
    limited = settings.model_copy(
        update={"history": settings.history.model_copy(update={"requests_per_minute": 2})}
    )
    fake = FakeMassive({"/v2/aggs/ticker/X/range/1/day/2024-10-10/2024-10-19": lambda _: {}})
    sleeps: list[float] = []
    client = history_client(limited, fake, sleeps)
    for _ in range(3):
        client.aggregates("X", 1, "day", date(2024, 10, 10), date(2024, 10, 19))
    assert sleeps == [60.0]


def test_untraded_atm_falls_back_to_next_strike() -> None:
    pre = NFLX.pre
    call_atm, put_atm = contract("call", 687.5), contract("put", 687.5)
    call_up, put_up = contract("call", 690), contract("put", 690)
    call_down, put_down = contract("call", 685), contract("put", 685)
    source = FakeSource(
        [call_atm, put_atm, call_up, put_up, call_down, put_down],
        {
            call_atm.ticker: [bar(pre - timedelta(days=1), 30)],  # накануне не торговался
            call_up.ticker: [bar(pre, 24.0)],
            put_up.ticker: [bar(pre - timedelta(days=1), 20)],  # пут не торговался
            call_down.ticker: [bar(pre, 27.0)],
            put_down.ticker: [bar(pre, 23.0)],
        },
    )
    settings = HISTORY
    bars = fetch_event_bars(source, "NFLX", NFLX, NFLX_SPOT, settings)
    assert source.aggregate_calls == [
        call_atm.ticker,  # колл ATM не торговался — пут не запрашиваем
        call_up.ticker,
        put_up.ticker,
        call_down.ticker,
        put_down.ticker,
    ]
    straddle = straddle_from_bars("NFLX", NFLX, NFLX_SPOT, bars, settings.risk_free_rate)
    assert (straddle.strike, straddle.straddle) == (685, 50.0)


def test_attempts_are_capped_and_missing_pair_is_data_error() -> None:
    pairs = [(contract("call", k), contract("put", k)) for k in (685, 687.5, 690, 692.5)]
    source = FakeSource([c for pair in pairs for c in pair], {})
    settings = HISTORY
    bars = fetch_event_bars(source, "NFLX", NFLX, NFLX_SPOT, settings)
    assert bars == []
    assert len(source.aggregate_calls) == settings.max_strike_attempts
    with pytest.raises(DataError, match="no option traded on 2024-10-17"):
        straddle_from_bars("NFLX", NFLX, NFLX_SPOT, bars, 0.04)


def test_no_contracts_is_data_error() -> None:
    with pytest.raises(DataError, match="no option contracts as of 2024-10-17"):
        fetch_event_bars(FakeSource([], {}), "NFLX", NFLX, NFLX_SPOT, HISTORY)


def test_straddle_uses_nearest_valid_expiration_and_lower_strike_on_tie() -> None:
    pre = NFLX.pre
    rows = [
        *option_bars(contract("call", 685), [bar(pre, 26)]),
        *option_bars(contract("put", 685), [bar(pre, 24)]),
        *option_bars(contract("call", 690), [bar(pre, 23)]),
        *option_bars(contract("put", 690), [bar(pre, 27)]),
        *option_bars(contract("call", 687.5, date(2024, 10, 25)), [bar(pre, 40)]),
        *option_bars(contract("put", 687.5, date(2024, 10, 25)), [bar(pre, 40)]),
        *option_bars(contract("call", 687.5), [bar(pre - timedelta(days=1), 1)]),  # не накануне
    ]
    straddle = straddle_from_bars("NFLX", NFLX, 687.5, rows, 0.04)
    assert (straddle.expiration, straddle.strike, straddle.straddle) == (
        date(2024, 10, 18),
        685,
        50,
    )


def test_only_one_leg_traded_is_data_error() -> None:
    rows = option_bars(contract("call", 687.5), [bar(NFLX.pre, 25)])
    with pytest.raises(DataError, match="both legs"):
        straddle_from_bars("NFLX", NFLX, NFLX_SPOT, rows, 0.04)


def test_unparseable_iv_is_none_not_a_guess() -> None:
    pre = NFLX.pre
    rows = [
        *option_bars(contract("call", 600), [bar(pre, 50.0)]),  # ниже внутренней стоимости 87,65
        *option_bars(contract("put", 600), [bar(pre, 0.5)]),
    ]
    straddle = straddle_from_bars("NFLX", NFLX, NFLX_SPOT, rows, 0.04)
    assert straddle.call_iv is None
    assert straddle.put_iv is not None


def test_other_contract_type_is_rejected() -> None:
    other = contract("call", 600).model_copy(update={"contract_type": "other"})
    with pytest.raises(DataError, match="unsupported contract type"):
        option_bars(other, [bar(NFLX.pre, 1)])


def test_stock_closes_and_spot() -> None:
    closes = stock_closes([bar(NFLX.pre, NFLX_SPOT), bar(NFLX.reaction, 760.0)])
    assert spot_on(closes, "NFLX", NFLX) == NFLX_SPOT
    with pytest.raises(DataError, match="no stock close on 2024-10-17"):
        spot_on({}, "NFLX", NFLX)
