from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.errors import DataError
from adapters.finnhub.models import FinnhubEarning
from adapters.massive.models import Bar, TickerChange
from backtest.mode_c_run import previous_days
from core.config import load_config
from core.db import models as orm
from core.db.store import save_report_facts, sync_universe
from core.domain.schedule import EventJob
from core.domain.types import SkipReason
from core.registry.protocols import DecisionContext, EventContext, Proposal, Skip
from core.session_guard import ET
from decision.report import parse_report, report_handlers, surprise_pct
from execution.costs import BrokerCostModel
from strategies.mode_c.strategy import ModeCStrategy

CONFIG = load_config()
COSTS = BrokerCostModel(CONFIG.broker.costs["manual"])
REPORT = date(2026, 10, 20)  # вторник, BMO — день реакции тот же
DECISION = datetime.combine(REPORT, time(10, 45), tzinfo=ET)


def bar(day: date, at: time, price: float, volume: float, vwap: float | None = None) -> Bar:
    start = datetime.combine(day, at, tzinfo=ET).timestamp() * 1000
    raw = {"o": price, "h": price + 1, "l": price - 1, "c": price, "v": volume, "t": start}
    if vwap is not None:
        raw["vw"] = vwap
    return Bar.model_validate(raw)


class Stocks:
    """Закрытия 100 (ATR 2); первый час прошлых дней — 60 минут по 100 акций."""

    def __init__(self, today_price: float = 102.0, today_volume: float = 300.0) -> None:
        self.today_price, self.today_volume = today_price, today_volume

    def aggregates(
        self, ticker: str, multiplier: int, timespan: str, *args: Any, **kwargs: Any
    ) -> list[Bar]:
        days = list(reversed(previous_days(REPORT, 40)))
        if timespan == "day":
            return [bar(d, time(0), 100, 1) for d in days]
        out = [
            bar(d, (datetime.combine(d, time(9, 30)) + timedelta(minutes=m)).time(), 100, 100)
            for d in days[-20:]
            for m in range(60)
        ]
        for m in range(60):  # к 10:45 с задержкой 15 минут есть минуты до 10:30
            at = (datetime.combine(REPORT, time(9, 30)) + timedelta(minutes=m)).time()
            out.append(bar(REPORT, at, self.today_price, self.today_volume, vwap=101.5))
        return out

    def ticker_changes(self, ticker: str) -> list[TickerChange]:
        return []


class Reports:
    def __init__(self, rows: list[FinnhubEarning]) -> None:
        self.rows, self.calls = rows, 0

    def earnings_calendar(
        self, start: date, end: date, symbol: str | None = None
    ) -> list[FinnhubEarning]:
        self.calls += 1
        return [r for r in self.rows if start <= r.date <= end and symbol in (None, r.symbol)]


def earning(eps: float | None = 1.10, revenue: float | None = 9.5e9) -> FinnhubEarning:
    return FinnhubEarning.model_validate(
        {
            "symbol": "NFLX",
            "date": REPORT.isoformat(),
            "hour": "bmo",
            "epsEstimate": 1.0,
            "epsActual": eps,
            "revenueEstimate": 1.0e10,
            "revenueActual": revenue,
        }
    )


@pytest.fixture
def event(session: Session) -> orm.Event:
    sync_universe(session, CONFIG.universe)
    row = orm.Event(ticker="NFLX", report_date=REPORT, report_time="BMO", date_status="confirmed")
    session.add(row)
    session.flush()
    return row


def ctx(session: Session, as_of: datetime = DECISION) -> DecisionContext:
    return DecisionContext(
        event=EventContext(
            event_id=1,
            ticker="NFLX",
            report_date=REPORT,
            report_time="BMO",
            stage="T0",
            as_of=as_of,
            session=session,
        ),
        features={},
        forecasts={},
    )


def strategy(stocks: Stocks | None = None, reports: Reports | None = None) -> ModeCStrategy:
    return ModeCStrategy(stocks or Stocks(), reports or Reports([]), COSTS, CONFIG.thresholds, 0.04)


def test_surprise_pct() -> None:
    assert surprise_pct(1.1, 1.0) == pytest.approx(10.0)
    assert surprise_pct(-0.9, -1.0) == pytest.approx(10.0)  # убыток меньше ожидаемого — плюс
    assert surprise_pct(1.0, 0.0) is None
    assert surprise_pct(None, 1.0) is None


def test_parse_report_records_facts(session: Session, event: orm.Event) -> None:
    job = EventJob(
        event_id=event.id, stage="T0", job="parse_report", kind="analysis", run_at=DECISION
    )
    assert parse_report(session, job, source=Reports([earning(eps=None)])) is None  # ещё нет факта
    assert session.scalars(select(orm.EarningsTrack)).first() is None
    facts = parse_report(session, job, source=Reports([earning()]))
    assert facts is not None
    row = session.scalars(select(orm.EarningsTrack)).one()
    assert (row.eps_actual, row.report_time) == (1.10, "BMO")
    assert row.eps_surprise_pct == pytest.approx(10.0)
    assert row.rev_surprise_pct == pytest.approx(-5.0)
    save_report_facts(session, "NFLX", REPORT, None, {"rev_actual": None})
    session.expire_all()
    assert session.scalars(select(orm.EarningsTrack)).one().rev_actual == 9.5e9  # не затёрто


def test_retry_handler_records_facts_the_first_run_missed(
    session: Session, event: orm.Event
) -> None:
    def job(name: str) -> EventJob:
        return EventJob(event_id=event.id, stage="T0", job=name, kind="analysis", run_at=DECISION)

    early = report_handlers(Reports([earning(eps=None)]))  # 07:30: факта в Finnhub ещё нет
    assert set(early) == {"parse_report", "parse_report_retry"}
    early["parse_report"](session, job("parse_report"))
    assert session.scalars(select(orm.EarningsTrack)).first() is None
    later = report_handlers(Reports([earning()]))  # 10:40: факт появился
    later["parse_report_retry"](session, job("parse_report_retry"))
    row = session.scalars(select(orm.EarningsTrack)).one()
    assert row.eps_actual == 1.10
    assert row.eps_surprise_pct == pytest.approx(10.0)


def test_surprise_uses_consensus_snapshot_before_reaction(
    session: Session, event: orm.Event
) -> None:
    event.fiscal_period = "2026Q3"
    session.add_all(
        [
            orm.ConsensusSnapshot(
                ticker="NFLX", fiscal_period="2026Q3", as_of=date(2026, 10, 19), eps_estimate=1.2
            ),
            # в день реакции BMO отчёт уже мог выйти — такой снимок не берётся
            orm.ConsensusSnapshot(
                ticker="NFLX", fiscal_period="2026Q3", as_of=REPORT, eps_estimate=0.5
            ),
        ]
    )
    session.flush()
    job = EventJob(
        event_id=event.id, stage="T0", job="parse_report", kind="analysis", run_at=DECISION
    )
    facts = parse_report(session, job, source=Reports([earning()]))  # в календаре оценка 1,0
    assert facts is not None
    assert facts.eps_consensus == 1.2
    assert facts.eps_surprise_pct == pytest.approx((1.10 - 1.2) / 1.2 * 100)
    assert facts.rev_consensus == 1.0e10  # выручки в снимке нет — оценка из календаря


def test_mode_c_enters_on_confirmed_surprise(session: Session, event: orm.Event) -> None:
    save_report_facts(session, "NFLX", REPORT, "BMO", {"eps_surprise_pct": 10.0})
    reports = Reports([])
    result = strategy(reports=reports).evaluate(ctx(session))
    assert isinstance(result, Proposal)
    assert (result.mode, result.construction) == ("C", "stock")
    assert 0 < result.cost_fraction < 0.1  # стоп 2 × ATR 2 = 4 на акцию
    assert reports.calls == 0  # сюрприз из earnings_track


def test_mode_c_asks_finnhub_when_report_not_parsed(session: Session, event: orm.Event) -> None:
    reports = Reports([earning(eps=0.85)])  # −15% — продажа, но цена выросла
    assert strategy(reports=reports).evaluate(ctx(session)) == Skip("mode_c", ["C_NOT_CONFIRMED"])
    assert reports.calls == 1
    short = strategy(Stocks(today_price=98.0), Reports([earning(eps=0.85)])).evaluate(ctx(session))
    assert isinstance(short, Proposal)
    assert short.construction == "stock_short"


@pytest.mark.parametrize(
    ("surprise", "stocks", "as_of", "reason"),
    [
        (3.0, Stocks(), DECISION, "C_NOT_CONFIRMED"),  # сюрприз ≤ 5%
        (10.0, Stocks(today_volume=150.0), DECISION, "C_NOT_CONFIRMED"),  # объём ≤ 2× среднего
        (10.0, Stocks(), DECISION - timedelta(days=1), "DATA_CALENDAR"),  # не день реакции
    ],
)
def test_mode_c_skips(
    session: Session,
    event: orm.Event,
    surprise: float,
    stocks: Stocks,
    as_of: datetime,
    reason: SkipReason,
) -> None:
    save_report_facts(session, "NFLX", REPORT, "BMO", {"eps_surprise_pct": surprise})
    assert strategy(stocks).evaluate(ctx(session, as_of)) == Skip("mode_c", [reason])


def test_mode_c_without_report_is_data_finnhub(session: Session, event: orm.Event) -> None:
    assert strategy().evaluate(ctx(session, DECISION.astimezone(UTC))) == Skip(
        "mode_c", ["DATA_FINNHUB"]
    )  # отчёта в Finnhub ещё нет — сбой данных, а не «сигнал не подтверждён»


class DownReports:
    def earnings_calendar(
        self, start: date, end: date, symbol: str | None = None
    ) -> list[FinnhubEarning]:
        raise DataError("finnhub", "HTTP 503")


def test_mode_c_finnhub_down_is_data_finnhub(session: Session, event: orm.Event) -> None:
    down = ModeCStrategy(Stocks(), DownReports(), COSTS, CONFIG.thresholds, 0.04)
    assert down.evaluate(ctx(session)) == Skip("mode_c", ["DATA_FINNHUB"])
