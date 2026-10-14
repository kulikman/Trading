"""Контрактные тесты API дашборда (T19a, DASHBOARD.md §5)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from api.app import create_app
from core.config import load_config
from core.db import models as orm
from core.db.store import save_reported_earnings, sync_universe, update_earnings
from core.domain.earnings import ReportedEarnings

CONFIG = load_config()
TOKEN = "test-token-for-contract-tests"  # noqa: S105 — тестовое значение
NOW = datetime(2026, 10, 14, 18, 0, tzinfo=UTC)  # среда 14:00 ET, основная сессия
AUTH = {"Authorization": f"Bearer {TOKEN}"}
# Целые поля, которые не являются числами для показа: идентификаторы, счётчики строк, интервалы.
PLAIN_INTS = {"card_id", "companies", "refresh_ms"}

ENDPOINTS = [
    "/api/status",
    "/api/account",
    "/api/account?mode=real",
    "/api/account/summary",
    "/api/account/summary?mode=real",
    "/api/changes",
    "/api/today",
    "/api/week",
    "/api/week/terminal",
    "/api/trades?state=open",
    "/api/trades?state=closed",
    "/api/journal",
    "/api/journal?filter=entered",
    "/api/journal?filter=skipped",
    "/api/sectors",
    "/api/sectors/banks",
    "/api/companies/GS/overview",
    "/api/companies/GS/news",
    "/api/companies/GS/reports",
    "/api/companies/GS/financials",
    "/api/companies/GS/track",
    "/api/system/models",
    "/api/system/plugins",
    "/api/system/errors",
]


@pytest.fixture
def client(session: Session) -> TestClient:
    app = create_app(
        engine=session.connection(), token=TOKEN, clock=lambda: NOW, thresholds=CONFIG.thresholds
    )
    return TestClient(app)


def add_event(
    session: Session, ticker: str, report_date: date, status: str | None = None, **decision: Any
) -> orm.Event:
    event = orm.Event(
        ticker=ticker, report_date=report_date, report_time="BMO", date_status="confirmed"
    )
    session.add(event)
    session.flush()
    if status is not None:
        session.add(
            orm.Decision(
                event_id=event.id,
                status=status,
                decided_at=datetime(2026, 10, 1, tzinfo=UTC),
                **decision,
            )
        )
        session.flush()
    return event


def add_trade(
    session: Session,
    ticker: str,
    report_date: date,
    pnl: float,
    closed: datetime,
    *,
    paper: bool = True,
    mode: str = "A",
) -> None:
    event = add_event(session, ticker, report_date, "ENTERED", mode=mode)
    decision_id = session.query(orm.Decision.id).filter_by(event_id=event.id).scalar()
    card = orm.TradeCard(
        decision_id=decision_id,
        state="CLOSED",
        paper=paper,
        legs=[],
        pnl_total=Decimal(str(pnl)),
        pnl_direction=Decimal(str(pnl)),
    )
    session.add(card)
    session.flush()
    session.add_all(
        [
            orm.TradeCardTransition(
                card_id=card.id,
                at=closed.replace(hour=13),
                from_state=None,
                to_state="OPEN",
                reason="вход",
            ),
            orm.TradeCardTransition(
                card_id=card.id, at=closed, from_state="OPEN", to_state="CLOSED", reason="цель"
            ),
        ]
    )
    session.flush()


@pytest.fixture
def seeded(session: Session) -> Session:
    sync_universe(session, CONFIG.universe)
    add_trade(session, "GS", date(2026, 10, 1), 500, datetime(2026, 10, 2, 15, tzinfo=UTC))
    add_trade(session, "JPM", date(2026, 10, 5), -200, datetime(2026, 10, 6, 15, tzinfo=UTC))
    add_trade(
        session, "MS", date(2026, 10, 7), 300, datetime(2026, 10, 14, 15, tzinfo=UTC), mode="C"
    )
    add_trade(
        session, "NFLX", date(2026, 10, 8), 9999, datetime(2026, 10, 9, 15, tzinfo=UTC), paper=False
    )  # Real — не должен попасть ни в один ответ Paper
    add_event(
        session, "BAC", date(2026, 10, 14), "SKIPPED", reasons=["EDGE_LOW"], shadow={"pnl": -150.0}
    )
    add_event(
        session, "WFC", date(2026, 10, 14), "SKIPPED", reasons=["PRE_RUN"], shadow={"pnl": 80.0}
    )
    add_event(session, "C", date(2026, 10, 16))
    save_reported_earnings(
        session,
        [
            ReportedEarnings(
                ticker="GS",
                report_date=date(2026, 10, 1),
                report_time="BMO",
                fiscal_period_end=date(2026, 9, 30),
                eps_consensus=10.0,
                eps_actual=11.0,
                eps_surprise_pct=10.0,
            )
        ],
    )
    update_earnings(session, "GS", date(2026, 10, 1), {"actual_move": 0.031})
    return session


def numbers_without_display(node: Any, key: str = "") -> list[str]:
    """Пути к числам, у которых нет пары value / display."""
    if isinstance(node, dict):
        if "value" in node and "display" in node:
            return []
        return [p for k, v in node.items() for p in numbers_without_display(v, f"{key}.{k}")]
    if isinstance(node, list):
        return [p for i, v in enumerate(node) for p in numbers_without_display(v, f"{key}[{i}]")]
    if isinstance(node, bool) or not isinstance(node, int | float):
        return []
    return [] if key.rsplit(".", 1)[-1] in PLAIN_INTS else [key]


@pytest.mark.parametrize("path", ENDPOINTS)
def test_every_endpoint_answers_and_numbers_have_display(
    seeded: Session, client: TestClient, path: str
) -> None:
    response = client.get(path, headers=AUTH)
    assert response.status_code == 200, response.text
    assert numbers_without_display(response.json()) == []


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": TOKEN}]
)
def test_request_without_valid_token_is_rejected(
    client: TestClient, headers: dict[str, str]
) -> None:
    assert client.get("/api/status", headers=headers).status_code == 401


def test_app_refuses_to_start_without_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DASHBOARD_API_TOKEN", raising=False)
    with pytest.raises(Exception, match="DASHBOARD_API_TOKEN"):
        create_app(thresholds=CONFIG.thresholds)


def test_account_bar_paper_by_hand_and_real_not_mixed(seeded: Session, client: TestClient) -> None:
    paper = client.get("/api/account", headers=AUTH).json()
    # 100 000 + 500 − 200 + 300; Real-сделка +9 999 не учтена
    assert paper["balance"] == {"value": 100600.0, "display": "$100 600", "tone": "neutral"}
    assert paper["pnl_today"]["display"] == "+$300"  # закрыта 14.10
    assert paper["pnl_month"]["value"] == 600
    assert paper["drawdown_threshold"]["display"] == "10%"
    assert paper["refresh_ms"] == 60_000  # основная сессия
    real = client.get("/api/account?mode=real", headers=AUTH).json()
    assert (real["is_available"], real["balance"]) == (False, None)
    closed = client.get("/api/trades?state=closed", headers=AUTH).json()
    assert [r["ticker"] for r in closed["closed"]] == ["MS", "JPM", "GS"]
    assert closed["total"] == "Сделок 3 · прибыльных 2 · итог +$600"


def test_account_summary_metrics_by_hand(seeded: Session, client: TestClient) -> None:
    summary = client.get("/api/account/summary", headers=AUTH).json()
    metrics = {m["metric"]: m["all_time"] for m in summary["metrics"]}
    assert metrics["Win rate"]["display"] == "66,7%"
    assert metrics["Profit factor"]["value"] == pytest.approx(800 / 200)
    assert metrics["Ожидаемая прибыль на сделку"]["display"] == "+$200"
    # пик 100 500 после GS, затем 100 300: просадка 200 / 100 500
    assert metrics["Максимальная просадка"]["value"] == pytest.approx(200 / 100500)
    assert metrics["P&L режим C"]["display"] == "+$300"
    assert metrics["Sharpe"]["display"] == "нет данных"  # 9 торговых дней < 20
    assert [p["balance"]["value"] for p in summary["curve"]] == [100500, 100300, 100600]
    # min 100 000 → y=156, max 100 600 → y=4 (высота 152); x: 02.10 → 4, 06.10 → 201,3, 14.10 → 596
    assert summary["curve_path"] == "M4,156.0 H4.0 V29.3 H201.3 V80.0 H596.0 V4.0 H596"
    path = {c["criterion"]: c for c in summary["path_to_real"]}
    assert path["СДЕЛОК"]["display"] == "СДЕЛОК 3/50"
    assert path["СДЕЛОК"]["tone"] == "negative"
    assert path["ПРОСАДКА"]["is_met"] is True


def test_today_week_and_journal(seeded: Session, client: TestClient) -> None:
    today = client.get("/api/today", headers=AUTH).json()
    assert [(r["ticker"], r["decision"], r["reason"]) for r in today["reports"]] == [
        ("BAC", "ПРОПУСК", "EDGE_LOW"),
        ("WFC", "ПРОПУСК", "PRE_RUN"),
    ]
    assert today["now"]["is_action"] is False
    week = client.get("/api/week", headers=AUTH).json()
    assert [e["ticker"] for e in week["events"]] == ["BAC", "WFC", "C"]  # пн 12.10 – пт 16.10
    assert week["top"] == []  # отбор недели — T16
    journal = client.get("/api/journal?filter=skipped", headers=AUTH).json()
    assert journal["summary"] == "Пропуски сэкономили $150 · упустили $80"
    assert {r["code"]: r["times"]["value"] for r in journal["reasons"]} == {
        "EDGE_LOW": 1,
        "PRE_RUN": 1,
    }


def test_errors_newest_first(seeded: Session, client: TestClient) -> None:
    seeded.add_all(
        [
            orm.ErrorLog(
                at=datetime(2026, 10, 14, 19, 0, tzinfo=UTC),
                source="options",
                ticker="NFLX",
                stage="T-7",
                error_type="DataError",
                message="HTTP 429",
            ),
            orm.ErrorLog(
                at=datetime(2026, 10, 14, 10, 0, tzinfo=UTC),
                source="calendar-daily",
                error_type="RuntimeError",
                message="finnhub down",
            ),
        ]
    )
    seeded.flush()
    rows = client.get("/api/system/errors?limit=5", headers=AUTH).json()["rows"]
    assert [(r["time"], r["source"], r["ticker"], r["message"]) for r in rows] == [
        ("14.10.2026 15:00 ET / 22:00 МСК", "options", "NFLX", "HTTP 429"),
        ("14.10.2026 06:00 ET / 13:00 МСК", "calendar-daily", "—", "finnhub down"),
    ]
    assert client.get("/api/system/errors?limit=0", headers=AUTH).status_code == 422


def test_company_track_and_not_found(seeded: Session, client: TestClient) -> None:
    track = client.get("/api/companies/gs/track", headers=AUTH).json()
    row = track["rows"][0]
    assert (row["surprise"]["display"], row["actual_move"]["display"]) == ("+10,0%", "+3,1%")
    assert row["decision"] == "ENTERED"
    assert client.get("/api/companies/XXX/track", headers=AUTH).status_code == 404
    assert client.get("/api/trades/999999", headers=AUTH).status_code == 404
    assert client.get("/api/sectors/none", headers=AUTH).status_code == 404
