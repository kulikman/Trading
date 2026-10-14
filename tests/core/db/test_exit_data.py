from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from adapters.massive.history import option_bars
from adapters.massive.models import Bar, OptionContract
from backtest.exit_data import ExitDataLoader
from backtest.load_exit_data import summary
from core.config import load_config
from core.db import models as orm
from core.db.store import (
    save_option_bars,
    save_reported_earnings,
    set_implied_move,
    sync_universe,
    update_earnings,
)
from core.domain.earnings import ReportedEarnings
from core.session_guard import ET

CONFIG = load_config()
TODAY = date(2026, 10, 14)
STRADDLE_DAY, CONDOR_DAY = date(2025, 10, 21), date(2026, 1, 20)  # AMC: реакция на следующий день
SPOT = {STRADDLE_DAY: 100.0, CONDOR_DAY: 90.0}
EXPIRATION = {STRADDLE_DAY: date(2025, 10, 24), CONDOR_DAY: date(2026, 1, 23)}


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


def bar(moment: datetime, close: float) -> Bar:
    return Bar.model_validate(
        {"o": close, "h": close, "l": close, "c": close, "v": 5, "t": moment.timestamp() * 1000}
    )


def day_bar(day: date, close: float) -> Bar:
    return bar(datetime.combine(day, time(0), tzinfo=ET), close)


class Options:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        strikes = range(60, 125, 5)
        expiry = EXPIRATION[CONDOR_DAY]
        self.contracts = [contract(k, s, expiry) for s in strikes for k in ("call", "put")]

    def option_contracts(self, underlying: str, **kwargs: Any) -> list[OptionContract]:
        self.calls.append(("contracts", str(kwargs["as_of"])))
        low, high = kwargs["strike_gte"], kwargs["strike_lte"]
        return [c for c in self.contracts if low <= c.strike_price <= high]

    def aggregates(
        self, ticker: str, multiplier: int, timespan: str, start: date, end: date, **kwargs: Any
    ) -> list[Bar]:
        self.calls.append((timespan, ticker))
        if timespan == "day":
            return [day_bar(CONDOR_DAY, 2.0)]
        reaction = start
        return [
            bar(datetime.combine(reaction, time(9, 20), tzinfo=ET), 9.0),  # до открытия — отброс
            bar(datetime.combine(reaction, time(9, 31), tzinfo=ET), 3.0),
            bar(datetime.combine(reaction, time(11, 0), tzinfo=ET), 2.5),
            bar(datetime.combine(reaction, time(11, 1), tzinfo=ET), 1.0),  # после выхода — отброс
        ]


class Stocks:
    def aggregates(self, *args: Any, **kwargs: Any) -> list[Bar]:
        return [day_bar(d, c) for d, c in SPOT.items()]


@pytest.fixture
def archive(session: Session) -> Session:
    sync_universe(session, CONFIG.universe)
    history = [date(2023, 1, 19), date(2023, 4, 18), date(2023, 7, 19), date(2023, 10, 18)]
    reports = [*history, STRADDLE_DAY, CONDOR_DAY]
    save_reported_earnings(
        session,
        [
            ReportedEarnings(
                ticker="NFLX",
                report_date=d,
                report_time="AMC",
                fiscal_period_end=d - timedelta(days=20),
            )
            for d in reports
        ],
    )
    for day in history:
        update_earnings(session, "NFLX", day, {"actual_move": 0.10})  # история: |движение| 10%
    set_implied_move(session, "NFLX", STRADDLE_DAY, 0.06)  # 10 / 6 = 1,67 → стрэддл
    set_implied_move(session, "NFLX", CONDOR_DAY, 0.15)  # 10 / 15 = 0,67 → iron condor
    for day, spot in SPOT.items():
        for kind in ("call", "put"):
            atm = contract(kind, spot, EXPIRATION[day])
            save_option_bars(session, option_bars(atm, [day_bar(day, 4.0)]))
    return session


def loader(options: Options) -> ExitDataLoader:
    return ExitDataLoader(
        options=options,
        stocks=Stocks(),
        settings=CONFIG.sources.massive.history,
        thresholds=CONFIG.thresholds,
        today=TODAY,
    )


def count(session: Session, model: Any) -> int:
    return session.execute(select(func.count()).select_from(model)).scalar_one()


def test_loads_straddle_minutes_and_condor_legs(archive: Session) -> None:
    options = Options()
    report = loader(options).load(archive, "NFLX")
    assert dict(report.signals) == {"straddle": 1, "iron_condor": 1}
    assert (report.ready["straddle"], report.ready["iron_condor"]) == (1, 1)
    assert report.minute_series_saved == 6  # 2 ноги стрэддла + 4 ноги кондора
    legs = [t for kind, t in options.calls if kind == "day"]
    assert legs == [  # длинный пут 65, короткий 75, короткий колл 105, длинный 115 (±1 / ±2 × 15%)
        "O:NFLX260123P00065000",
        "O:NFLX260123P00075000",
        "O:NFLX260123C00105000",
        "O:NFLX260123C00115000",
    ]
    minutes = archive.scalars(select(orm.OptionMinuteBar.minute)).all()
    assert len(minutes) == 12  # по 2 минуты на ногу: 09:31 и 11:00
    assert {m.astimezone(ET).time() for m in minutes} == {time(9, 31), time(11, 0)}
    assert count(archive, orm.OptionDailyBar) == 4 + 4


def test_rerun_downloads_nothing_new(archive: Session) -> None:
    loader(Options()).load(archive, "NFLX")
    options = Options()
    report = loader(options).load(archive, "NFLX")
    assert report.minute_series_saved == 0
    assert [c for c in options.calls if c[0] != "contracts"] == []


def test_missing_atm_pair_is_reported_not_raised(archive: Session) -> None:
    archive.execute(delete(orm.OptionDailyBar))
    report = loader(Options()).load(archive, "NFLX")
    assert len(report.failures) == 2
    assert "no option traded" in report.failures[0][1]
    assert "без данных 2" in summary(report)


def test_minute_bar_timestamps_are_utc_aware(archive: Session) -> None:
    loader(Options()).load(archive, "NFLX")
    first = archive.scalars(
        select(orm.OptionMinuteBar.minute).order_by(orm.OptionMinuteBar.minute)
    ).first()
    assert first is not None
    assert first == datetime(2025, 10, 22, 13, 31, tzinfo=UTC)  # 09:31 EDT
