from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.app import create_app
from core.config import load_config
from core.db import models as orm
from core.db.store import sync_universe
from decision.week import select_week, week_window
from notify.digest import morning_text

CONFIG = load_config()
MONDAY = date(2026, 10, 19)
AT = datetime(2026, 10, 16, 19, 15, tzinfo=UTC)


def event(session: Session, ticker: str, day: date) -> orm.Event:
    row = orm.Event(ticker=ticker, report_date=day, report_time="AMC", date_status="confirmed")
    session.add(row)
    session.flush()
    return row


def proposal(
    session: Session, row: orm.Event, strategy: str, construction: str, p: float, mode: str = "move"
) -> None:
    session.add(
        orm.DecisionStep(
            event_id=row.id,
            stage="T-1",
            job=f"{strategy}_decision",
            strategy_id=strategy,
            is_shadow=False,
            outcome="proposal",
            mode=mode,
            construction=construction,
            reasons=[],
            edge=0.05,
            confidence=p,
            probability=p,
            cost_fraction=0.02,
            risk_fraction=0.01,
            at=AT,
        )
    )
    session.flush()


def test_window_is_next_five_trading_days() -> None:
    assert week_window(MONDAY) == (date(2026, 10, 19), date(2026, 10, 23))
    assert week_window(date(2026, 10, 17)) == (date(2026, 10, 19), date(2026, 10, 23))  # суббота
    assert week_window(date(2026, 10, 22)) == (date(2026, 10, 22), date(2026, 10, 28))


def test_ranked_by_expected_profit_not_confidence(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    nflx, tsla = (
        event(session, "NFLX", date(2026, 10, 20)),
        event(session, "TSLA", date(2026, 10, 21)),
    )
    gs, ms = event(session, "GS", date(2026, 10, 22)), event(session, "MS", date(2026, 10, 30))
    proposal(session, nflx, "straddle", "straddle", 0.55)  # 1000 × (0,55 − 0,45) = 100
    proposal(session, tsla, "straddle", "straddle", 0.60)  # 200
    proposal(session, tsla, "iron_condor", "iron_condor", 0.58)  # 160 — у события лучшая — 200
    proposal(session, gs, "mode_c", "stock", 0.0, mode="C")  # без модели — в топ не идёт
    proposal(session, ms, "straddle", "straddle", 0.90)  # вне окна 5 торговых дней
    selection = select_week(session, MONDAY, CONFIG.thresholds)
    assert [(p.event.ticker, round(p.expected_usd or 0)) for p in selection.top] == [
        ("TSLA", 200),
        ("NFLX", 100),
    ]
    assert selection.top[0].construction == "straddle"
    assert [p.event.ticker for p in selection.rest] == ["GS"]
    lines = morning_text(session, datetime(2026, 10, 19, 12, 30, tzinfo=UTC), CONFIG.thresholds)
    assert "1. 21.10 TSLA · стрэддл · ожидаемая прибыль +$200" in lines.splitlines()
    assert "22.10 GS · после закрытия · ждём решения" in lines.splitlines()


def test_week_api_top_columns(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    proposal(session, event(session, "TSLA", date(2026, 10, 21)), "straddle", "straddle", 0.60)
    app = create_app(
        engine=session.connection(),
        token="t",  # noqa: S106 — тестовое значение
        clock=lambda: datetime(2026, 10, 19, 12, 0, tzinfo=UTC),
        thresholds=CONFIG.thresholds,
    )
    week = TestClient(app).get("/api/week", headers={"Authorization": "Bearer t"}).json()
    assert week["top"] == [
        {
            "№": "1",
            "Тикер": "TSLA",
            "Дата и время": "21.10.2026 AMC",
            "Режим": "движение",
            "Конструкция": "стрэддл",
            "Ожидаемая прибыль": "+$200",
            "Уверенность": "60%",
        }
    ]
    assert week["events"] == []
