from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from backtest import daily_archive
from backtest.daily_archive import DailyArchive, DueReport, due_reports, run_daily_archive
from core.config import load_config
from core.db import models as orm
from core.db.store import save_reported_earnings, sync_universe
from core.domain.earnings import ReportedEarnings
from execution.paper import PaperRunResult
from learning.shadow import ShadowRunResult

CONFIG = load_config()
TODAY = date(2026, 10, 14)  # среда; 5 торговых дней назад — 07.10
UNIVERSE = set(CONFIG.universe.tickers())


def event(ticker: str, day: date, time_of_day: str) -> orm.Event:
    return orm.Event(
        ticker=ticker, report_date=day, report_time=time_of_day, date_status="projected"
    )


@pytest.fixture
def calendar(session: Session) -> Session:
    sync_universe(session, CONFIG.universe)
    session.add_all(
        [
            event("NFLX", date(2026, 10, 9), "BMO"),  # реакция 09.10 — в окне, отчёт уже в архиве
            event("GS", date(2026, 10, 13), "BMO"),  # реакция 13.10 — в окне, нового отчёта нет
            event("JPM", date(2026, 10, 13), "AMC"),  # реакция 14.10 — сегодня, рано
            event("MS", date(2026, 9, 30), "BMO"),  # старше окна
        ]
    )
    save_reported_earnings(
        session,
        [
            ReportedEarnings(
                ticker="NFLX",
                report_date=date(2026, 10, 9),
                report_time="BMO",
                fiscal_period_end=date(2026, 9, 30),
                eps_actual=1.0,
            )
        ],
    )
    session.flush()
    return session


def test_due_reports_window_and_refresh_flag(calendar: Session) -> None:
    due = due_reports(calendar, TODAY, 5, UNIVERSE)
    assert due == [
        DueReport("GS", date(2026, 10, 13), needs_dates=True),
        DueReport("NFLX", date(2026, 10, 9), needs_dates=False),
    ]
    assert due_reports(calendar, TODAY, 5, {"NFLX"}) == [due[1]]  # не из вселенной — пропуск


class Builder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    def build(self, session: Session, ticker: str, *, refresh_dates: bool = False) -> Any:
        self.calls.append((ticker, refresh_dates))
        return ticker


class Exits:
    def __init__(self) -> None:
        self.calls: list[tuple[str, date | None]] = []

    def load(self, db: Session, ticker: str, *, since: date | None = None) -> Any:
        self.calls.append((ticker, since))
        return ticker


def archive(builder: Builder, exits: Exits) -> DailyArchive:
    return DailyArchive(
        builder=builder,
        exits=exits,
        lookback_trading_days=5,
        tickers=UNIVERSE,
    )


class Shadows:
    def __init__(self) -> None:
        self.calls: list[tuple[date, date]] = []

    def run(self, session: Session, today: date, retry_since: date) -> ShadowRunResult:
        self.calls.append((today, retry_since))
        return ShadowRunResult({"closed": 1})


class Paper:
    def __init__(self) -> None:
        self.calls: list[tuple[date, date]] = []

    def run(self, session: Session, today: date, retry_since: date) -> PaperRunResult:
        self.calls.append((today, retry_since))
        return PaperRunResult({"CLOSED": 1})


def test_run_computes_shadows_after_exit_data(calendar: Session) -> None:
    shadows, paper = Shadows(), Paper()
    result = DailyArchive(
        builder=Builder(),
        exits=Exits(),
        lookback_trading_days=5,
        tickers=UNIVERSE,
        shadows=shadows,
        paper=paper,
    ).run(calendar, TODAY)
    assert shadows.calls == [(TODAY, date(2026, 10, 7))]  # no_data повторяется 5 торговых дней
    assert paper.calls == [(TODAY, date(2026, 10, 7))]
    assert result.shadows == ShadowRunResult({"closed": 1})
    assert result.paper == PaperRunResult({"CLOSED": 1})


def test_run_refreshes_dates_only_for_new_reports(calendar: Session) -> None:
    builder, exits = Builder(), Exits()
    result = archive(builder, exits).run(calendar, TODAY)
    assert builder.calls == [("GS", True), ("NFLX", False)]  # Alpha Vantage — только для GS
    assert exits.calls == [("GS", date(2026, 10, 13)), ("NFLX", date(2026, 10, 9))]
    assert len(result.due) == 2


def test_scheduled_run_skips_non_trading_day_and_uses_factory(
    calendar: Session, engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    built: list[date] = []

    def factory(config: Any, today: date) -> DailyArchive:
        built.append(today)
        return archive(Builder(), Exits())

    saturday = datetime(2026, 10, 17, 22, 30, tzinfo=UTC)
    assert run_daily_archive(now=lambda: saturday, factory=factory) is None
    monkeypatch.setattr(daily_archive, "engine", lambda: engine)
    wednesday = datetime(2026, 10, 14, 22, 30, tzinfo=UTC)  # 18:30 EDT
    result = run_daily_archive(now=lambda: wednesday, factory=factory)
    assert result is not None
    assert built == [TODAY]
