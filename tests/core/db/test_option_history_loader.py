from datetime import date, datetime, time, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from adapters.alphavantage.models import AvEarnings
from adapters.errors import DataError
from adapters.massive.models import Bar, OptionContract
from backtest.option_history import EarningsSourceExhausted, OptionHistoryLoader
from core.config import load_config
from core.db import models as orm
from core.db.store import earnings_dates, save_earnings_dates, save_option_bars, sync_universe
from core.domain.options import OptionDailyBar
from core.session_guard import ET

TODAY = date(2026, 10, 14)
CONFIG = load_config()
HISTORY = CONFIG.sources.massive.history

# Отчёты NFLX (AMC): два с ценами опционов, один без контрактов, один вне окна доступа (2 года).
TRADED = {
    date(2025, 10, 21): (date(2025, 10, 24), 100.0),
    date(2026, 1, 20): (date(2026, 1, 23), 90.0),
}
NO_CONTRACTS = date(2026, 7, 16)
TOO_OLD = date(2024, 7, 18)


def bar(day: date, close: float) -> Bar:
    start = datetime.combine(day, time(0), tzinfo=ET).timestamp() * 1000
    return Bar.model_validate({"o": close, "h": close, "l": close, "c": close, "v": 50, "t": start})


def contract(kind: str, strike: float, expiration: date) -> OptionContract:
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


class Options:
    """ATM-пара на каждый отчёт из TRADED; пре-день = день отчёта (AMC)."""

    def __init__(self) -> None:
        self.contract_calls = 0
        self.aggregate_calls: list[str] = []
        self.contracts: list[OptionContract] = []
        self.bars: dict[str, list[Bar]] = {}
        for report, (expiration, spot) in TRADED.items():
            for kind, price in (("call", 4.0), ("put", 3.0)):
                item = contract(kind, spot, expiration)
                self.contracts.append(item)
                self.bars[item.ticker] = [bar(report - timedelta(days=1), 1.0), bar(report, price)]

    def option_contracts(self, underlying: str, **kwargs: Any) -> list[OptionContract]:
        self.contract_calls += 1
        low, high = kwargs["expiration_gte"], kwargs["expiration_lte"]
        return [c for c in self.contracts if low <= c.expiration_date <= high]

    def aggregates(self, ticker: str, *args: Any, **kwargs: Any) -> list[Bar]:
        self.aggregate_calls.append(ticker)
        return self.bars.get(ticker, [])


class Stocks:
    def __init__(self) -> None:
        self.calls: list[tuple[date, date, bool]] = []

    def aggregates(
        self,
        ticker: str,
        multiplier: int,
        timespan: str,
        start: date,
        end: date,
        *,
        adjusted: bool = True,
    ) -> list[Bar]:
        self.calls.append((start, end, adjusted))
        closes = {d: spot for d, (_, spot) in TRADED.items()} | {NO_CONTRACTS: 80.0}
        return [bar(d, c) for d, c in closes.items()]


class Earnings:
    def __init__(self, error: DataError | None = None) -> None:
        self.error = error
        self.calls = 0

    def earnings(self, symbol: str) -> AvEarnings:
        self.calls += 1
        if self.error is not None:
            raise self.error
        reports = [*TRADED, NO_CONTRACTS, TOO_OLD]
        return AvEarnings.model_validate(
            {
                "symbol": symbol,
                "quarterlyEarnings": [
                    {
                        "fiscalDateEnding": "2026-06-30",
                        "reportedDate": d.isoformat(),
                        "reportTime": "post-market",
                    }
                    for d in reports
                ],
            }
        )


def loader(
    options: Options, earnings: Earnings, stocks: Stocks | None = None
) -> OptionHistoryLoader:
    return OptionHistoryLoader(
        options=options, stocks=stocks or Stocks(), earnings=earnings, settings=HISTORY, today=TODAY
    )


@pytest.fixture
def universe(session: Session) -> Session:
    sync_universe(session, CONFIG.universe)
    return session


def implied_moves(session: Session) -> dict[date, float | None]:
    rows = session.execute(
        select(orm.EarningsTrack.report_date, orm.EarningsTrack.implied_move).where(
            orm.EarningsTrack.ticker == "NFLX"
        )
    ).all()
    return {r.report_date: r.implied_move for r in rows}


def test_first_run_downloads_saves_and_computes(universe: Session) -> None:
    options, earnings, stocks = Options(), Earnings(), Stocks()
    report = loader(options, earnings, stocks).load(universe, "NFLX")
    assert earnings.calls == 1
    assert [s.days.report_date for s in report.straddles] == list(TRADED)
    assert [s.move for s in report.straddles] == [pytest.approx(0.07), pytest.approx(7 / 90)]
    assert [d for d, _ in report.failures] == [NO_CONTRACTS]
    assert report.bars_saved == 8
    assert report.from_archive == 0
    assert implied_moves(universe) == {
        date(2025, 10, 21): pytest.approx(0.07),
        date(2026, 1, 20): pytest.approx(7 / 90),
        NO_CONTRACTS: None,
    }  # отчёт старше окна доступа не записан
    assert stocks.calls == [(date(2025, 10, 11), date(2026, 7, 17), False)]  # без поправки на сплит
    assert earnings_dates(universe, "NFLX", date(2024, 1, 1))[0] == (date(2025, 10, 21), "AMC")


def test_rerun_uses_archive_and_stored_dates(universe: Session) -> None:
    loader(Options(), Earnings()).load(universe, "NFLX")
    options, earnings = Options(), Earnings()
    report = loader(options, earnings).load(universe, "NFLX")
    assert earnings.calls == 0  # даты уже в earnings_track
    assert options.aggregate_calls == []  # цены — из архива
    assert options.contract_calls == 1  # только отчёт без данных проверяется снова
    assert report.from_archive == 2
    assert len(report.straddles) == 2
    count = universe.execute(select(func.count()).select_from(orm.OptionDailyBar)).scalar_one()
    assert count == 8


def test_archived_event_without_pair_is_not_redownloaded(universe: Session) -> None:
    report_day = date(2025, 10, 21)
    lone_call = OptionDailyBar(
        option_ticker="O:NFLX251024C00100000",
        day=report_day,
        underlying="NFLX",
        expiration=date(2025, 10, 24),
        strike=100,
        option_type="call",
        open=4,
        high=4,
        low=4,
        close=4,
        volume=1,
    )
    save_option_bars(universe, [lone_call])
    options = Options()
    report = loader(options, Earnings()).load(universe, "NFLX")
    assert (report_day, f"NFLX {report_day}: no strike with both legs traded on {report_day}") in [
        (d, r) for d, r in report.failures
    ]
    assert "O:NFLX251024C00100000" not in options.aggregate_calls


def test_alphavantage_limit_stops_the_run(universe: Session) -> None:
    with pytest.raises(EarningsSourceExhausted, match="NFLX: Note: 25 requests per day"):
        loader(Options(), Earnings(DataError("alphavantage", "Note: 25 requests per day"))).load(
            universe, "NFLX"
        )


def test_stale_stored_dates_are_refreshed(universe: Session) -> None:
    save_earnings_dates(universe, "NFLX", [(date(2025, 1, 21), "AMC")])
    earnings = Earnings()
    loader(Options(), earnings).load(universe, "NFLX")
    assert earnings.calls == 1


def test_known_report_time_is_not_overwritten_with_unknown(universe: Session) -> None:
    save_earnings_dates(universe, "NFLX", [(date(2026, 7, 16), "AMC")])
    save_earnings_dates(universe, "NFLX", [(date(2026, 7, 16), None)])
    assert earnings_dates(universe, "NFLX", date(2026, 1, 1)) == [(date(2026, 7, 16), "AMC")]


def test_no_reports_in_window_does_nothing(universe: Session) -> None:
    class OnlyOld(Earnings):
        def earnings(self, symbol: str) -> AvEarnings:
            return AvEarnings.model_validate(
                {
                    "symbol": symbol,
                    "quarterlyEarnings": [
                        {"fiscalDateEnding": "2024-06-30", "reportedDate": TOO_OLD.isoformat()}
                    ],
                }
            )

    stocks = Stocks()
    report = loader(Options(), OnlyOld(), stocks).load(universe, "NFLX")
    assert (report.events, stocks.calls) == (0, [])
