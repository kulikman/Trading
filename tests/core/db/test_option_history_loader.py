from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from adapters.alphavantage.models import AvEarnings
from adapters.errors import DataError
from backtest.option_history import EarningsSourceExhausted, OptionHistoryLoader
from core.db import models as orm
from core.db.store import (
    earnings_dates,
    save_option_bars,
    save_reported_earnings,
    sync_universe,
)
from core.domain.earnings import ReportedEarnings
from core.domain.options import OptionDailyBar
from tests.core.db.archive_fakes import (
    CONFIG,
    HISTORY,
    NO_CONTRACTS,
    TODAY,
    TOO_OLD,
    TRADED,
    Earnings,
    Options,
    Stocks,
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
        TOO_OLD: None,  # старше окна доступа опционов: только EPS, без implied move
    }
    assert stocks.calls == [(date(2025, 10, 11), date(2026, 7, 17), False)]  # без поправки на сплит
    assert earnings_dates(universe, "NFLX", date(2024, 1, 1))[0] == (TOO_OLD, "AMC")


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


def reported(day: date, report_time: Any = "AMC", eps: float | None = 1.0) -> ReportedEarnings:
    return ReportedEarnings(
        ticker="NFLX",
        report_date=day,
        report_time=report_time,
        fiscal_period_end=day - timedelta(days=20),
        eps_actual=eps,
    )


def test_stale_stored_dates_are_refreshed(universe: Session) -> None:
    save_reported_earnings(universe, [reported(date(2025, 1, 21))])
    earnings = Earnings()
    loader(Options(), earnings).load(universe, "NFLX")
    assert earnings.calls == 1


def test_fresh_dates_without_eps_are_refetched(universe: Session) -> None:
    save_reported_earnings(universe, [reported(NO_CONTRACTS, eps=None)])  # как после T10
    earnings = Earnings()
    loader(Options(), earnings).load(universe, "NFLX")
    assert earnings.calls == 1
    row = universe.scalars(
        select(orm.EarningsTrack).where(orm.EarningsTrack.report_date == NO_CONTRACTS)
    ).one()
    assert (row.eps_consensus, row.eps_actual, row.eps_surprise_pct) == (1.0, 1.1, 10.0)
    assert row.fiscal_period_end == date(2026, 6, 30)


def test_known_report_time_is_not_overwritten_with_unknown(universe: Session) -> None:
    save_reported_earnings(universe, [reported(date(2026, 7, 16))])
    save_reported_earnings(universe, [reported(date(2026, 7, 16), None)])
    assert earnings_dates(universe, "NFLX", date(2026, 1, 1)) == [(date(2026, 7, 16), "AMC")]


def test_duplicate_dates_in_one_batch_keep_the_last(universe: Session) -> None:
    saved = save_reported_earnings(
        universe, [reported(date(2026, 7, 16), eps=1.0), reported(date(2026, 7, 16), eps=2.0)]
    )
    assert saved == 1
    row = universe.scalars(select(orm.EarningsTrack)).one()
    assert row.eps_actual == 2.0


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
