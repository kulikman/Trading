"""Контрактные тесты API дашборда (T19a, DASHBOARD.md §5)."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from api.app import create_app
from api.events import pending_hint
from core.config import load_config
from core.db import models as orm
from core.db.store import save_reported_earnings, sync_universe, update_earnings
from core.domain.broker import Fill, Order
from core.domain.earnings import ReportedEarnings
from execution.cash import record_cash

CONFIG = load_config()
TOKEN = "test-token-for-contract-tests"  # noqa: S105 — тестовое значение
NOW = datetime(2026, 10, 14, 18, 0, tzinfo=UTC)  # среда 14:00 ET, основная сессия
AUTH = {"Authorization": f"Bearer {TOKEN}"}
# Целые поля, которые не являются числами для показа: идентификаторы, счётчики строк, интервалы.
PLAIN_INTS = {"card_id", "decision_id", "companies", "refresh_ms"}

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


def test_real_from_cash_and_open_position_on_bar(seeded: Session, client: TestClient) -> None:
    at = datetime(2026, 10, 1, tzinfo=UTC)
    record_cash(seeded, "deposit", Decimal("50000"), "старт", at)
    record_cash(seeded, "withdraw", Decimal("1000"), None, at)
    real = client.get("/api/account?mode=real", headers=AUTH).json()
    assert real["is_available"] is True
    assert real["balance"]["value"] == 50000 - 1000 + 9999  # пополнения − вывод + Real-сделка
    event = add_event(
        seeded,
        "NFLX",
        date(2026, 10, 13),
        "ENTERED",
        mode="C",
        strategy_id="mode_c",
        construction="stock",
    )
    seeded.add(
        orm.DecisionStep(
            event_id=event.id,
            stage="T0",
            job="mode_c_decision",
            strategy_id="mode_c",
            is_shadow=False,
            outcome="proposal",
            mode="C",
            construction="stock",
            risk_fraction=0.01,
            at=at,
        )
    )
    decision_id = seeded.query(orm.Decision.id).filter_by(event_id=event.id).scalar()
    seeded.add(
        orm.TradeCard(
            decision_id=decision_id,
            state="OPEN",
            paper=True,
            legs=[
                {
                    "symbol": "NFLX",
                    "instrument": "stock",
                    "side": "buy",
                    "quantity": 10,
                    "multiplier": 1,
                }
            ],
            fills=[
                {
                    "symbol": "NFLX",
                    "side": "buy",
                    "quantity": 10,
                    "price": 105.0,
                    "at": "2026-10-13T14:45:00+00:00",
                    "purpose": "entry",
                }
            ],
            stop={"rule": "трейлинг 2 × ATR(14)", "price": None},
            trailing={
                "atr": 2.0,
                "multiple": 2.0,
                "stop": 101.29,
                "updated_at": "2026-10-14T20:20:00+00:00",
            },
        )
    )
    seeded.flush()
    paper = client.get("/api/account", headers=AUTH).json()
    assert paper["in_trades"]["value"] == 1050  # 10 × 105
    assert paper["free"]["value"] == 100600 - 1050
    assert paper["risk"]["value"] == pytest.approx(1000 / 100600)  # 1% от 100 000
    assert paper["worst_drawdown"]["value"] == pytest.approx(1000 / 100600)  # пик 100 600
    row = client.get("/api/trades?state=open", headers=AUTH).json()["open"][0]
    assert (row["ticker"], row["entry"]["value"], row["stop"]["value"]) == ("NFLX", 1050, 101.29)
    assert row["pnl"]["display"] != "+$0"  # котировок нет — не ноль
    card = seeded.query(orm.TradeCard).filter(orm.TradeCard.state == "CLOSED").first()
    assert card is not None
    card.costs = Decimal("12.5")
    seeded.flush()
    metrics = {
        m["metric"]: m["all_time"]
        for m in client.get("/api/account/summary", headers=AUTH).json()["metrics"]
    }
    assert metrics["Издержки"]["value"] == 12.5


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
    assert week["top"] == []  # решений с вероятностью модели нет — топ пуст
    assert week["top_message"].startswith("нет событий с ожидаемой прибылью")
    journal = client.get("/api/journal?filter=skipped", headers=AUTH).json()
    assert journal["summary"] == "Пропуски сэкономили $150 · упустили $80"
    assert {r["code"]: r["times"]["value"] for r in journal["reasons"]} == {
        "EDGE_LOW — нет сигнала или преимущество не выше издержек": 1,
        "PRE_RUN — сильный рост перед отчётом без причины": 1,
    }


def test_journal_rows_have_trade_id_status_and_reason(seeded: Session, client: TestClient) -> None:
    add_event(seeded, "META", date(2026, 10, 14), "SKIPPED", reasons=["C_NOT_CONFIRMED"])
    rows = client.get("/api/journal", headers=AUTH).json()["rows"]
    by_ticker = {r["ticker"]: r for r in rows}
    gs_card = seeded.scalars(
        select(orm.TradeCard.id)
        .join(orm.Decision, orm.Decision.id == orm.TradeCard.decision_id)
        .join(orm.Event, orm.Event.id == orm.Decision.event_id)
        .where(orm.Event.ticker == "GS")
    ).one()
    assert by_ticker["GS"]["status"] == "Открыта"
    assert by_ticker["GS"]["card_id"] == gs_card  # ID сделки = номер карточки
    assert by_ticker["GS"]["reasons"].startswith("предложение стратегии прошло ворота решения")
    assert by_ticker["META"]["status"] == "Пропущена"
    assert by_ticker["META"]["card_id"] is None  # у пропуска сделки нет
    assert by_ticker["META"]["reasons"] == (
        "C_NOT_CONFIRMED — сюрприз не подтвердился ценой и объёмом"
    )
    assert len({r["decision_id"] for r in rows}) == len(rows)


def test_pending_hint_explains_what_is_awaited_and_when() -> None:
    now = datetime(2026, 10, 22, 12, 29, tzinfo=UTC)
    at = datetime(2026, 10, 22, 14, 45, tzinfo=UTC)  # 10:45 ET = 17:45 МСК
    when = "решение режима C в 10:45 ET / 17:45 МСК"
    assert pending_hint(6.139, at, 0.05, now) == (
        "C",
        f"кандидат на покупку: сюрприз EPS +6,1% выше порога 5%; {when}",
    )
    assert pending_hint(-8.0, at, 0.05, now)[1].startswith("кандидат на продажу: сюрприз EPS −8,0%")
    assert pending_hint(2.0, at, 0.05, now)[1] == (
        f"сюрприз EPS +2,0% не выше порога 5% — вход не ожидается; {when}"
    )
    assert pending_hint(None, at, 0.05, now)[1] == f"факт отчёта ещё не получен; {when}"
    assert pending_hint(6.1, None, 0.05, now)[1] == (
        "кандидат на покупку: сюрприз EPS +6,1% выше порога 5%"  # задачи решения нет — без времени
    )
    after = datetime(2026, 10, 22, 15, 0, tzinfo=UTC)
    assert pending_hint(6.1, at, 0.05, after)[1].endswith(
        "решение режима C было в 10:45 ET / 17:45 МСК, записи ещё нет"
    )


def test_today_shows_candidate_and_decision_time_for_event_without_decision(
    seeded: Session, client: TestClient
) -> None:
    event = add_event(seeded, "LMT", date(2026, 10, 14))  # отчёт сегодня, решения ещё нет
    seeded.add_all(
        [
            orm.EarningsTrack(
                ticker="LMT",
                report_date=date(2026, 10, 14),
                eps_consensus=7.509,
                eps_actual=7.97,
                eps_surprise_pct=6.139,
            ),
            orm.EventJob(
                event_id=event.id,
                stage="T0",
                job="mode_c_decision",
                kind="execution",
                run_at=datetime(2026, 10, 14, 19, 45, tzinfo=UTC),  # позже «сейчас» (18:00 UTC)
            ),
        ]
    )
    seeded.flush()
    rows = client.get("/api/today", headers=AUTH).json()["reports"]
    [lmt] = [r for r in rows if r["ticker"] == "LMT"]
    assert lmt["decision"] == "ЖДЁМ"
    assert lmt["mode"] == "C"
    assert lmt["reason"] == (
        "кандидат на покупку: сюрприз EPS +6,1% выше порога 5%; "
        "решение режима C в 15:45 ET / 22:45 МСК"
    )


def test_several_entries_per_event(seeded: Session, client: TestClient) -> None:
    event = add_event(
        seeded,
        "MS",
        date(2026, 10, 14),
        "ENTERED",
        mode="move",
        strategy_id="straddle",
        construction="straddle",
    )
    seeded.add(
        orm.Decision(
            event_id=event.id,
            status="ENTERED",
            mode="C",
            strategy_id="mode_c",
            construction="stock",
            decided_at=datetime(2026, 10, 14, tzinfo=UTC),
        )
    )
    seeded.flush()
    today = client.get("/api/today", headers=AUTH).json()
    assert [(r["ticker"], r["mode"]) for r in today["reports"] if r["ticker"] == "MS"] == [
        ("MS", "move"),
        ("MS", "C"),
    ]  # «Сегодня» — строка на каждый вход
    week = client.get("/api/week", headers=AUTH).json()
    assert [e["ticker"] for e in week["events"]].count("MS") == 1  # неделя — строка на событие


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
    assert [(r["level"], r["tone"]) for r in rows] == [
        ("ошибка", "negative"),
        ("ошибка", "negative"),
    ]
    status = client.get("/api/status", headers=AUTH).json()
    assert status["headline"] == "СИСТЕМА: СБОЙ options, calendar-daily"
    options_error = seeded.scalars(
        select(orm.ErrorLog).where(orm.ErrorLog.source == "options")
    ).one()
    options_error.resolved_at = datetime(2026, 10, 14, 19, 30, tzinfo=UTC)  # перезапуск прошёл
    seeded.flush()
    resolved = client.get("/api/system/errors", headers=AUTH).json()["rows"][0]
    assert (resolved["level"], resolved["tone"], resolved["report"]) == (
        "решено 14.10.2026 15:30 ET / 22:30 МСК",
        "positive",
        None,
    )
    status = client.get("/api/status", headers=AUTH).json()
    assert status["headline"] == "СИСТЕМА: СБОЙ calendar-daily"  # options решено
    report = rows[0]["report"]
    assert "Задача: options" in report
    assert "Тикер: NFLX · стадия: T-7" in report
    assert "Текст: HTTP 429" in report
    assert client.get("/api/system/errors?limit=0", headers=AUTH).status_code == 422


def test_status_sources_and_system_messages(seeded: Session, client: TestClient) -> None:
    at = datetime(2026, 10, 14, 13, 0, tzinfo=UTC)
    seeded.add_all(
        [
            orm.SourceStatus(source="massive", last_ok_at=at),
            orm.SourceStatus(
                source="finnhub",
                last_ok_at=at,
                last_error_at=at + timedelta(hours=1),
                last_error="HTTP 503",
            ),
            orm.SystemMessage(at=at, code="DATA_CALENDAR", text="СИСТЕМА · сбой calendar-daily"),
        ]
    )
    seeded.flush()
    status = client.get("/api/status", headers=AUTH).json()
    sources = {r["source"]: (r["status"], r["last_success"]) for r in status["sources"]}
    assert sources["Massive"] == ("ОК", "14.10.2026 09:00 ET / 16:00 МСК")
    assert sources["Finnhub"][0] == "СБОЙ"  # ошибка позже последнего успеха
    assert sources["Alpha Vantage"] == ("нет данных", "—")
    assert sources["брокер"][0] == "ручной брокер — без подключения"
    assert status["messages"] == ["14.10.2026 09:00 ET / 16:00 МСК — СИСТЕМА · сбой calendar-daily"]


def test_heartbeat_for_watchdog(seeded: Session, client: TestClient) -> None:
    skipped = client.get("/api/system/heartbeat", headers=AUTH).json()
    assert skipped["problems"] == ["пропуски без сообщения: 2"]  # пропуски без «ПРОПУСК»
    for decision in seeded.scalars(select(orm.Decision).where(orm.Decision.status == "SKIPPED")):
        decision.tg_message_id = -1  # как миграция 0019 для решений до T18
    seeded.flush()
    assert client.get("/api/system/heartbeat", headers=AUTH).json()["ok"] is True
    seeded.add(orm.SystemMessage(at=NOW - timedelta(minutes=10), text="СИСТЕМА · сбой x"))
    seeded.execute(
        text(
            "INSERT INTO apscheduler_jobs (id, next_run_time, job_state)"
            " VALUES ('digest-morning', :t, '')"
        ),
        {"t": (NOW - timedelta(minutes=30)).timestamp()},
    )
    seeded.flush()
    beat = client.get("/api/system/heartbeat?watchdog=true", headers=AUTH).json()
    assert beat["ok"] is False
    assert beat["problems"] == [
        "задача digest-morning не запускалась с 13:30 ET / 20:30 МСК",
        "сообщения «СИСТЕМА» не отправлены: 1",
    ]
    status = client.get("/api/status", headers=AUTH).json()
    watchdog = next(r for r in status["sources"] if r["source"] == "сторож")
    assert watchdog["status"] == "ОК"  # проверка сторожа отмечена


def test_models_screen_lists_versions(seeded: Session, client: TestClient) -> None:
    assert client.get("/api/system/models", headers=AUTH).json()["message"] == (
        "моделей нет: make models-init"
    )
    seeded.add(
        orm.ModelVersion(
            model="p_up",
            version="0.1.0",
            params={"intercept": 0.0},
            metrics=None,
            trained_at=datetime(2026, 10, 14, 4, 0, tzinfo=UTC),
            accepted=True,
            reason="стартовая версия",
        )
    )
    seeded.flush()
    row = client.get("/api/system/models", headers=AUTH).json()["rows"][0]
    assert (row["model"], row["version"], row["trained"]) == (
        "p_up — рост цены",
        "0.1.0",
        "14.10.2026",
    )
    assert row["brier"]["display"] == "нет — стартовая версия, без обучения"
    assert row["accepted"] == "да — стартовая версия"


def test_dashboard_audit_fixes(seeded: Session, client: TestClient) -> None:
    reports = client.get("/api/companies/GS/reports", headers=AUTH).json()
    assert reports["message"] is None
    assert reports["reports"][0]["date"] == "01.10.2026"  # прошлый отчёт из архива
    assert reports["reports"][0]["urls"][0].endswith(
        "CIK=GS&type=8-K&dateb=20261002&owner=include&count=10"
    )
    for metric, value in (("revenue", 1000.0), ("gross_profit", 400.0), ("net_income", 150.0)):
        seeded.add(
            orm.FinancialQuarter(
                ticker="GS",
                metric=metric,
                period_end=date(2026, 9, 30),
                period_start=date(2026, 7, 1),
                value=value,
                unit="USD",
                derived=False,
                concept=metric,
                form="10-Q",
                accession=f"0000-{metric}",
                filed=date(2026, 10, 14),
            )
        )
    seeded.flush()
    rows = client.get("/api/companies/GS/financials", headers=AUTH).json()["rows"]
    margins = {r["metric"]: r["values"][0]["display"] for r in rows if "маржа" in r["metric"]}
    eps = next(r for r in rows if r["metric"] == "EPS (разводнённая)")
    assert eps["values"][0]["display"] == "$11,00 (отчёт)"  # Q4 / нет XBRL — EPS из истории отчётов
    assert margins == {"Валовая маржа": "40,0%", "Чистая маржа": "15,0%"}
    overview = client.get("/api/companies/GS/overview", headers=AUTH).json()
    assert overview["sector_id"] == "banks"  # ссылка на сектор в хлебных крошках
    assert overview["options"] == "нет данных архива"
    path = {
        c["criterion"]: c["display"]
        for c in client.get("/api/account/summary", headers=AUTH).json()["path_to_real"]
    }
    assert path["SHARPE"].startswith("SHARPE считается с 20 торговых дней")
    assert all(
        p["flagged"] == "решит отчёт сезона (T20)"
        for p in client.get("/api/system/plugins", headers=AUTH).json()
    )


def test_changes_readable_and_next_report_not_passed(seeded: Session, client: TestClient) -> None:
    event = seeded.scalars(select(orm.Event).where(orm.Event.ticker == "BAC")).first()
    assert event is not None
    seeded.add(
        orm.EventChange(
            event_id=event.id,
            at=NOW - timedelta(hours=1),
            field="date_check",
            old_value=None,
            new_value="mismatch",
            reason="DATA_CALENDAR: finnhub 2026-10-14 vs alphavantage 2026-10-15",
        )
    )
    seeded.flush()
    rows = client.get("/api/changes", headers=AUTH).json()["rows"]
    assert rows[0]["text"] == (
        "BAC: сверка даты — → даты расходятся (finnhub 2026-10-14 против alphavantage 2026-10-15)"
    )
    now = client.get("/api/today", headers=AUTH).json()["now"]["message"]
    assert "BAC" not in now  # отчёт BAC 14.10 BMO уже вышел (сейчас 14:00 ET)
    assert now == "Действий нет. Ближайший отчёт: C 16.10.2026"


def test_company_track_and_not_found(seeded: Session, client: TestClient) -> None:
    track = client.get("/api/companies/gs/track", headers=AUTH).json()
    row = track["rows"][0]
    assert (row["surprise"]["display"], row["actual_move"]["display"]) == ("+10,0%", "+3,1%")
    assert row["decision"] == "ENTERED"
    assert client.get("/api/companies/XXX/track", headers=AUTH).status_code == 404
    assert client.get("/api/trades/999999", headers=AUTH).status_code == 404
    assert client.get("/api/sectors/none", headers=AUTH).status_code == 404


def test_trust_line_costs_paper_vs_real(client: TestClient, session: Session) -> None:
    before = client.get("/api/trades", headers=AUTH).json()
    assert before["trust_line"].endswith(
        "Издержки Paper против реальности: нет данных до реальных исполнений"
    )
    assert before["trust_tone"] == "neutral"
    order = Order(
        client_order_id="card-1-leg-1",
        symbol="GS",
        instrument="stock",
        side="buy",
        quantity=10,
        multiplier=1,
        order_type="stop",
        purpose="entry",
        stop_price=100.0,
    )
    fill = Fill(
        order_id="m-1",
        client_order_id=order.client_order_id,
        symbol="GS",
        instrument="stock",
        side="buy",
        quantity=10,
        multiplier=1,
        price=101.0,  # на доллар хуже стопа — далеко за порогом модели
        at=NOW,
    )
    session.add(
        orm.BrokerOrder(
            order_id="m-1",
            client_order_id=order.client_order_id,
            payload=order.model_dump(mode="json"),
            instruction="—",
            status="filled",
            fill=fill.model_dump(mode="json"),
        )
    )
    session.flush()
    after = client.get("/api/trades", headers=AUTH).json()
    assert "реальные выше модели" in after["trust_line"]
    assert "(1 исполнение), вывод — от 20" in after["trust_line"]
    assert after["trust_tone"] == "neutral"  # одно исполнение — вывода нет, строка не красная
