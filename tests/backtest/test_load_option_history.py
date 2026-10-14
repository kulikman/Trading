from datetime import date

import pytest

from adapters.massive.history import EventDays, HistoricalStraddle
from backtest.load_option_history import parse_args, summary
from backtest.option_history import TickerReport

UNIVERSE = ["GS", "NFLX", "TSLA"]


def test_parse_ticker_list_is_uppercased() -> None:
    assert parse_args(["--ticker", "nflx", "--ticker", "GS"], UNIVERSE) == ["NFLX", "GS"]


def test_parse_all_is_the_universe() -> None:
    assert parse_args(["--all"], UNIVERSE) == UNIVERSE


@pytest.mark.parametrize("argv", [[], ["--ticker", "ZZZZ"], ["--all", "--ticker", "GS"]])
def test_parse_rejects_bad_arguments(argv: list[str]) -> None:
    with pytest.raises(SystemExit):
        parse_args(argv, UNIVERSE)


def test_summary_line() -> None:
    straddle = HistoricalStraddle(
        ticker="NFLX",
        days=EventDays.of(date(2024, 10, 17), "AMC"),
        expiration=date(2024, 10, 18),
        strike=687.5,
        spot=687.65,
        call_close=25.57,
        put_close=25.27,
        call_volume=381,
        put_volume=683,
        call_iv=1.7,
        put_iv=1.7,
    )
    report = TickerReport("NFLX", straddles=[straddle], failures=[(date(2026, 7, 16), "x")])
    assert summary(report) == (
        "NFLX: отчётов 2, с implied move 1, из архива 0, цен сохранено 0, без данных 1 "
        "| 2024-10-17 7.4%"
    )
