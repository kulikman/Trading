from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from agents.macro.daily import update_market_level
from api.app import create_app
from core.config import load_config
from core.db import models as orm
from core.risk.market import market_level_before
from tests.agents.test_macro_positioning import CLOSE_DAY, Fred, Stocks, bar, trading_days_until

THRESHOLDS = load_config().thresholds
TODAY = date(2026, 10, 14)  # закрытие накануне — 13.10


def sources() -> tuple[Fred, Stocks]:
    days = trading_days_until(CLOSE_DAY, 10)
    vix: list[tuple[date, float | None]] = [(d, 15.0) for d in days[:-1]]
    vix.append((CLOSE_DAY, 26.0))  # рост 15 → 26 за день — красный
    return Fred({"VIXCLS": vix}), Stocks([bar(d, 500.0) for d in days])


def test_daily_level_is_stored_for_every_day_and_rerun_updates(session: Session) -> None:
    fred, stocks = sources()
    row = update_market_level(session, fred, stocks, THRESHOLDS, TODAY)
    assert row is not None
    assert (row.day, row.level, row.vix, row.spy) == (CLOSE_DAY, "red", 26.0, 500.0)
    stored = session.scalars(select(orm.MarketLevelDay).order_by(orm.MarketLevelDay.day)).all()
    assert len(stored) == 10
    assert stored[0].level == "green"
    update_market_level(session, fred, stocks, THRESHOLDS, TODAY)  # повтор — без дублей
    assert len(session.scalars(select(orm.MarketLevelDay)).all()) == 10


def test_level_before_day_uses_previous_close(session: Session) -> None:
    fred, stocks = sources()
    update_market_level(session, fred, stocks, THRESHOLDS, TODAY)
    assert market_level_before(session, TODAY) == "red"  # решение 14.10 — по закрытию 13.10
    assert market_level_before(session, CLOSE_DAY) == "green"  # 13.10 — по закрытию 12.10
    assert market_level_before(session, date(2020, 1, 1)) is None


def test_market_plaque_reads_daily_level(session: Session) -> None:
    fred, stocks = sources()
    update_market_level(session, fred, stocks, THRESHOLDS, TODAY)
    session.flush()
    app = create_app(
        engine=session.connection(),
        token="t",  # noqa: S106 — тестовое значение
        clock=lambda: datetime(2026, 10, 14, 12, 0, tzinfo=UTC),
        thresholds=THRESHOLDS,
    )
    market = (
        TestClient(app).get("/api/status", headers={"Authorization": "Bearer t"}).json()["market"]
    )
    assert (market["level"], market["tone"], market["as_of"]) == (
        "КРАСНЫЙ",
        "action",
        "закрытие 13.10",
    )
    assert market["vix"]["value"] == 26.0
