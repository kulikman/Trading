from datetime import date
from typing import Any

import pytest

from adapters.massive.client import MassiveClient
from adapters.massive.models import Bar, TickerChange
from adapters.massive.symbols import daily_bars, symbol_periods
from core.config.sources import MassiveSettings
from tests.adapters.massive.conftest import FakeMassive, make_client

META = [
    TickerChange(date=date(2012, 5, 18), ticker="FB"),
    TickerChange(date=date(2022, 6, 9), ticker="META"),
]


def test_rename_history_is_used_when_last_change_is_current_ticker() -> None:
    assert symbol_periods("META", META) == [(date.min, "FB"), (date(2022, 6, 9), "META")]


@pytest.mark.parametrize(
    "changes",
    [[], [TickerChange(date=date(2015, 10, 6), ticker="GOOG")]],  # GOOGL: запись про класс C
)
def test_unrelated_or_empty_history_uses_current_ticker(changes: list[TickerChange]) -> None:
    assert symbol_periods("GOOGL", changes) == [(date.min, "GOOGL")]


class Source:
    def __init__(self, changes: list[TickerChange]) -> None:
        self.changes = changes
        self.calls: list[tuple[str, date, date, bool]] = []

    def ticker_changes(self, ticker: str) -> list[TickerChange]:
        return self.changes

    def aggregates(
        self,
        ticker: str,
        multiplier: int,
        timespan: Any,
        start: date,
        end: date,
        *,
        adjusted: bool = True,
    ) -> list[Bar]:
        self.calls.append((ticker, start, end, adjusted))
        return []


def test_bars_are_stitched_across_the_rename() -> None:
    source = Source(META)
    daily_bars(source, "META", date(2021, 10, 14), date(2022, 12, 31))
    assert source.calls == [
        ("FB", date(2021, 10, 14), date(2022, 6, 8), False),
        ("META", date(2022, 6, 9), date(2022, 12, 31), False),
    ]


def test_window_after_rename_asks_only_current_ticker() -> None:
    source = Source(META)
    daily_bars(source, "META", date(2024, 1, 1), date(2024, 2, 1))
    assert [c[0] for c in source.calls] == ["META"]


def test_client_parses_ticker_events(settings: MassiveSettings) -> None:
    body = {
        "results": {
            "name": "Meta Platforms",
            "events": [
                {
                    "ticker_change": {"ticker": "META"},
                    "type": "ticker_change",
                    "date": "2022-06-09",
                },
                {"ticker_change": {"ticker": "FB"}, "type": "ticker_change", "date": "2012-05-18"},
                {"type": "other", "date": "2020-01-01"},
            ],
        },
        "status": "OK",
    }  # ответ записан вживую 14.10.2026 (без request_id), плюс событие другого типа
    client: MassiveClient = make_client(
        settings, FakeMassive({"/vX/reference/tickers/META/events": lambda _: body})
    )
    assert client.ticker_changes("META") == META
