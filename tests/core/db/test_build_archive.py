from datetime import date
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.edgar.models import CompanyFacts, Filing
from adapters.errors import DataError
from backtest.build_archive import ArchiveBuilder, TickerArchive, parse_args, summary
from backtest.coverage import Coverage, coverage, render
from backtest.option_history import OptionHistoryLoader
from core.db import models as orm
from core.db.store import sync_universe
from tests.core.db.archive_fakes import (
    CONFIG,
    HISTORY,
    NO_CONTRACTS,
    TODAY,
    Earnings,
    Options,
    Stocks,
)

OCT, JAN = date(2025, 10, 21), date(2026, 1, 20)
NFLX_CIK = 1065280


def fact(start: str, end: str, value: float) -> dict[str, Any]:
    return {"start": start, "end": end, "val": value, "accn": "x", "form": "10-Q", "filed": end}


def filing(day: str, accepted: str) -> Filing:
    return Filing.model_validate(
        {
            "cik": NFLX_CIK,
            "form": "8-K",
            "accession_number": f"0001065280-{day}",
            "filing_date": day,
            "accepted_at": accepted,
            "primary_document": "x.htm",
            "items": "2.02,9.01",
        }
    )


class Sec:
    def __init__(self, error: DataError | None = None, ciks: dict[str, int] | None = None) -> None:
        self.error = error
        self.ciks = {"NFLX": NFLX_CIK} if ciks is None else ciks
        self.cik_calls = 0
        self.since: list[date | None] = []

    def ticker_ciks(self) -> dict[str, int]:
        self.cik_calls += 1
        return self.ciks

    def company_facts(self, cik: int) -> CompanyFacts:
        if self.error is not None:
            raise self.error
        revenue = [
            fact(
                "2025-06-29", "2025-09-27", 11.5e9
            ),  # 52/53 недели: конец квартала не в конце месяца
            fact("2025-09-28", "2025-12-31", 12.0e9),
        ]
        return CompanyFacts.model_validate(
            {
                "cik": cik,
                "entityName": "Netflix",
                "facts": {"us-gaap": {"Revenues": {"units": {"USD": revenue}}}},
            }
        )

    def earnings_releases(self, cik: int, since: date | None = None) -> list[Filing]:
        self.since.append(since)
        return [
            filing("2025-10-21", "2025-10-21T20:01:00Z"),  # 16:01 ET — тот же день
            filing("2026-02-25", "2026-02-25T21:00:00Z"),  # далеко от 20.01 — дата под сомнением
        ]


def builder(
    sec: Sec, earnings: Earnings | None = None, predecessors: dict[str, list[int]] | None = None
) -> ArchiveBuilder:
    stocks = Stocks()
    loader = OptionHistoryLoader(
        options=Options(),
        stocks=stocks,
        earnings=earnings or Earnings(),
        settings=HISTORY,
        today=TODAY,
    )
    return ArchiveBuilder(
        loader=loader,
        stocks=stocks,
        sec=sec,
        edgar=CONFIG.sources.edgar,
        today=TODAY,
        predecessor_ciks=predecessors,
    )


@pytest.fixture
def universe(session: Session) -> Session:
    sync_universe(session, CONFIG.universe)
    return session


def track(session: Session) -> dict[date, orm.EarningsTrack]:
    session.expire_all()
    rows = session.scalars(select(orm.EarningsTrack).where(orm.EarningsTrack.ticker == "NFLX"))
    return {r.report_date: r for r in rows}


def test_build_fills_moves_revenue_and_date_checks(universe: Session) -> None:
    sec = Sec()
    result = builder(sec).build(universe, "NFLX")
    rows = track(universe)
    oct_, jan = rows[OCT], rows[JAN]
    assert oct_.actual_move == pytest.approx(0.10)
    assert oct_.move_ratio == pytest.approx(0.10 / 0.07)
    assert jan.actual_move == pytest.approx(-0.05)
    assert jan.move_ratio == pytest.approx(0.05 / (7 / 90))
    assert rows[NO_CONTRACTS].actual_move == pytest.approx(0.05)
    assert rows[NO_CONTRACTS].move_ratio is None  # implied move нет
    assert (oct_.rev_actual, jan.rev_actual, rows[NO_CONTRACTS].rev_actual) == (11.5e9, 12e9, None)
    assert (oct_.date_check, oct_.sec_filing_date) == ("ok", OCT)
    assert (jan.date_check, jan.sec_filing_date) == ("mismatch", date(2026, 2, 25))
    assert (rows[NO_CONTRACTS].date_check, rows[NO_CONTRACTS].sec_filing_date) == ("no_8k", None)
    stats = result.stats
    assert (result.reports, stats.moves, stats.ratios, stats.revenue_matched) == (3, 3, 2, 2)
    assert sec.since == [date(2025, 9, 6)]  # первый отчёт окна − 45 дней поиска 8-K
    revenue = universe.scalars(
        select(orm.FinancialQuarter).where(orm.FinancialQuarter.ticker == "NFLX")
    ).all()
    assert len(revenue) == 2


def test_rebuild_is_idempotent_and_ciks_are_read_once(universe: Session) -> None:
    sec = Sec()
    archive = builder(sec)
    archive.build(universe, "NFLX")
    first = {d: (r.actual_move, r.rev_actual, r.date_check) for d, r in track(universe).items()}
    archive.build(universe, "NFLX")
    second = {d: (r.actual_move, r.rev_actual, r.date_check) for d, r in track(universe).items()}
    assert first == second
    assert sec.cik_calls == 1


def test_sec_outage_keeps_moves(universe: Session) -> None:
    builder(Sec(error=DataError("edgar", "HTTP 503"))).build(universe, "NFLX")
    rows = track(universe)
    assert rows[OCT].actual_move == pytest.approx(0.10)
    assert (rows[OCT].rev_actual, rows[OCT].date_check) == (None, None)


def test_unknown_cik_skips_sec_steps(universe: Session) -> None:
    result = builder(Sec(ciks={})).build(universe, "NFLX")
    assert (result.stats.moves, result.stats.revenue_matched, result.checks) == (3, 0, [])


def test_missing_dates_are_pending_without_other_steps(universe: Session) -> None:
    earnings = Earnings(DataError("alphavantage", "Information: limit"))
    result = builder(Sec(), earnings).build(universe, "NFLX")
    assert (result.dates_pending, result.reports) == (True, 0)


def test_coverage_report(universe: Session) -> None:
    result = builder(Sec()).build(universe, "NFLX")
    since = TODAY.replace(year=TODAY.year - 2)
    rows = coverage(universe, since, TODAY)
    assert rows == [Coverage("NFLX", reports=3, eps=3, revenue=2, implied=2, actual=3, full=2)]
    text = render(rows, result.checks, since=since, until=TODAY, pending=["CRM"])
    assert "| NFLX | 3 | 3 | 2 | 2 | 3 | 2 (67%) |" in text
    assert "| **Всего** | 3 | 3 | 2 | 2 | 3 | 2 (67%) |" in text
    assert "Ещё не загружены (лимит Alpha Vantage): CRM." in text
    assert "совпадает (0–1 день) — 1, расхождение — 1, нет 8-K рядом — 1" in text
    assert "| NFLX | 20.01.2026 | 25.02.2026 | 36 |" in text
    assert "| NFLX | 16.07.2026 | нет |  |" in text


def test_empty_coverage_renders_dash() -> None:
    text = render([], [], since=date(2024, 10, 14), until=TODAY, pending=[])
    assert "| **Всего** | 0 | 0 | 0 | 0 | 0 | 0 (—) |" in text


def test_summary_and_args() -> None:
    result = TickerArchive("CRM", dates_pending=True)
    assert summary(result).endswith("даты отчётов — в следующий запуск (лимит Alpha Vantage)")
    assert parse_args(["--ticker", "nflx"], ["NFLX", "GS"]) == ["NFLX"]
    with pytest.raises(SystemExit):
        parse_args(["--ticker", "ZZZZ"], ["NFLX"])


OLD_CIK = 34088


class ReorganizedSec(Sec):
    """История — под прежним CIK, новый регистрант — только последние подачи (как у XOM)."""

    def company_facts(self, cik: int) -> CompanyFacts:
        if cik == OLD_CIK:
            revenue = [
                fact("2025-06-29", "2025-09-27", 11.5e9),
                fact("2025-09-28", "2025-12-31", 99e9),
            ]
        else:
            revenue = [fact("2025-09-28", "2025-12-31", 12.0e9)]
        return CompanyFacts.model_validate(
            {
                "cik": cik,
                "entityName": "x",
                "facts": {"us-gaap": {"Revenues": {"units": {"USD": revenue}}}},
            }
        )

    def earnings_releases(self, cik: int, since: date | None = None) -> list[Filing]:
        self.since.append(since)
        if cik == OLD_CIK:
            return [filing("2025-10-21", "2025-10-21T20:01:00Z")]
        return [filing("2026-02-25", "2026-02-25T21:00:00Z")]


def test_predecessor_cik_history_is_merged(universe: Session) -> None:
    sec = ReorganizedSec()
    builder(sec, predecessors={"NFLX": [OLD_CIK]}).build(universe, "NFLX")
    rows = track(universe)
    assert rows[OCT].rev_actual == 11.5e9  # только у прежнего регистранта
    assert rows[JAN].rev_actual == 12e9  # у обоих — значение текущего
    assert (rows[OCT].date_check, rows[JAN].date_check) == ("ok", "mismatch")
    assert len(sec.since) == 2  # 8-K искали под обоими CIK


def test_universe_lists_predecessor_ciks() -> None:
    assert CONFIG.universe.sec_predecessor_ciks() == {"XOM": [34088]}
