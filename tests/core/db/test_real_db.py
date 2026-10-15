from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.broker.base import CardOrders
from adapters.broker.factory import create_card_orders
from adapters.broker.order_store import Ticket
from core.db import models as orm
from core.domain.broker import Fill, Order, OrderId, Quote
from core.registry.protocols import Proposal
from decision.chief import run_decision
from execution.cash import record_cash
from notify.bot import handle_callback, handle_reply
from notify.signals import send_new_signals
from strategies.mode_c.strategy import stock_plan
from tests.core.db.test_decision_db import CONFIG, FakeStrategy, event, job

__all__ = ["event"]  # фикстура события — из test_decision_db

PLAN = stock_plan("NFLX", 1, 100.0, 4.0, 0.01)  # лимит 100, стоп 96, риск акции 4,04
NOW = datetime(2026, 10, 21, 14, 45, tzinfo=UTC)  # день реакции 10:45 ET — решение режима C


def mode_c(plan: bool = True) -> dict[str, FakeStrategy]:
    result = Proposal(
        strategy_id="mode_c",
        mode="C",
        construction="stock",
        edge=0.0,
        confidence=0.0,
        probability=0.0,
        cost_fraction=0.01,
        plan=PLAN if plan else None,
    )
    return {"mode_c": FakeStrategy("mode_c", result)}


def go_live(session: Session, stage: str = "live", weight: float = 1.0) -> None:
    row = session.get(orm.Plugin, ("mode_c", "0.1.0"))
    assert row is not None
    row.stage, row.weight = stage, weight
    session.flush()


def orders(session: Session) -> CardOrders:
    return create_card_orders(
        quote_source=lambda s: Quote(symbol=s, bid=1, ask=1.1, at=NOW),
        no_market_orders_first_minutes=5,
        session_factory=lambda: Session(
            bind=session.connection(), join_transaction_mode="create_savepoint"
        ),
        clock=lambda: NOW,
    )


def run(session: Session, row: orm.Event, plan: bool = True) -> None:
    run_decision(
        session,
        job(row.id, "mode_c_decision", "T0"),
        ["mode_c"],
        mode_c(plan),
        config=CONFIG,
        now=NOW,
        orders=orders(session),
    )


def real_cards(session: Session) -> list[orm.TradeCard]:
    return list(session.scalars(select(orm.TradeCard).where(orm.TradeCard.paper.is_(False))))


def skips(session: Session) -> list[str]:
    return list(
        session.scalars(select(orm.SystemMessage.text).where(orm.SystemMessage.code == "REAL_SKIP"))
    )


def test_live_strategy_opens_real_card_with_orders(session: Session, event: orm.Event) -> None:
    go_live(session)
    record_cash(session, "deposit", Decimal("10000"), None, NOW)
    run(session, event)
    (card,) = real_cards(session)
    # 1% × зелёный × вес 1 × 0,5 (первые 30 дней) × $10 000 = $50 → 12 акций по $4,04
    assert (card.state, card.risk_usd) == ("ARMED", Decimal("48.48"))
    assert card.legs == [
        {"symbol": "NFLX", "instrument": "stock", "side": "buy", "quantity": 12.0, "multiplier": 1}
    ]
    assert card.stop == {"rule": "трейлинг 2 × ATR(14), старт 96.00", "price": 96.0}
    tickets = session.scalars(
        select(orm.BrokerOrder)
        .where(orm.BrokerOrder.card_id == card.id)
        .order_by(orm.BrokerOrder.client_order_id)
    ).all()
    assert [t.instruction for t in tickets] == [
        "Купить  NFLX  12 шт.  лимит ≤ 100.00",
        "Продать  NFLX  12 шт.  стоп 96.00 (только основная сессия)",
    ]
    paper = session.scalars(select(orm.TradeCard).where(orm.TradeCard.paper.is_(True))).all()
    assert len(paper) == 1  # paper-карточка остаётся — сбор данных
    assert skips(session) == []


class Client:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(
        self,
        text: str,
        *,
        silent: bool = False,
        buttons: list[tuple[str, str]] | None = None,
        reply_to: int | None = None,
    ) -> int:
        self.sent.append(text)
        return len(self.sent)

    def edit(
        self, message_id: int, text: str, *, buttons: list[tuple[str, str]] | None = None
    ) -> None:
        self.sent.append(text)


def test_real_message_and_fill_confirms_entry_only(session: Session, event: orm.Event) -> None:
    go_live(session)
    record_cash(session, "deposit", Decimal("10000"), None, NOW)
    run(session, event)
    client = Client()
    send_new_signals(session, client, CONFIG.thresholds)
    real = next(t for t in client.sent if "REAL" in t)
    assert "ОРДЕР  Купить  NFLX  12 шт.  лимит ≤ 100.00" in real
    assert "ОРДЕР  Продать  NFLX  12 шт.  стоп 96.00 (только основная сессия)" in real
    assert "РИСК   $48 (счёт Real)" in real
    (card,) = real_cards(session)
    broker = orders(session)
    assert (
        handle_callback(session, f"fill:{card.id}", broker, NOW, client)
        == "Ответьте ценой исполнения"
    )
    assert card.fill_prompt_id is not None
    assert handle_reply(session, "100.05", card.fill_prompt_id, broker, NOW) == (
        "Исполнение записано: 100.05"
    )
    statuses = session.scalars(
        select(orm.BrokerOrder.status)
        .where(orm.BrokerOrder.card_id == card.id)
        .order_by(orm.BrokerOrder.client_order_id)
    ).all()
    assert statuses == ["filled", "pending"]  # стоп остаётся стоять у брокера
    assert card.state == "OPEN"


def test_real_not_opened_reasons(session: Session, event: orm.Event) -> None:
    go_live(session)
    run(session, event)  # пополнений нет
    assert real_cards(session) == []
    assert skips(session) == [
        "СИСТЕМА · Real не открыт: NFLX mode_c — счёт Real не пополнен (make cash)"
    ]


def test_real_too_small_for_one_unit(session: Session, event: orm.Event) -> None:
    go_live(session, "live_small", 0.05)  # вес 5%: риск $2,50 < $4,04
    record_cash(session, "deposit", Decimal("10000"), None, NOW)
    run(session, event)
    assert real_cards(session) == []
    assert skips(session) == [
        "СИСТЕМА · Real не открыт: NFLX mode_c — риск $2.50 меньше одной единицы ($4.04)"
    ]


def test_paper_stage_has_no_real_card(session: Session, event: orm.Event) -> None:
    record_cash(session, "deposit", Decimal("10000"), None, datetime(2026, 9, 1, tzinfo=UTC))
    run(session, event)  # mode_c в paper
    assert real_cards(session) == []
    assert skips(session) == []


class Broken:
    """Ручной брокер, который падает: Real не открыт, paper-решение остаётся."""

    def place_for_card(self, order: Order, card_id: int) -> OrderId:
        raise RuntimeError("брокер недоступен")

    def pending_for_card(self, card_id: int) -> list[Ticket]:
        return []

    def confirm_fill(self, order_id: OrderId, *, price: float, at: datetime) -> Fill:
        raise NotImplementedError

    def cancel(self, order_id: OrderId) -> None:
        raise NotImplementedError


def test_real_failure_keeps_paper_decision(session: Session, event: orm.Event) -> None:
    go_live(session)
    record_cash(session, "deposit", Decimal("10000"), None, NOW)
    run_decision(
        session,
        job(event.id, "mode_c_decision", "T0"),
        ["mode_c"],
        mode_c(),
        config=CONFIG,
        now=NOW,
        orders=Broken(),
    )
    assert real_cards(session) == []
    paper = session.scalars(select(orm.TradeCard).where(orm.TradeCard.paper.is_(True))).all()
    assert len(paper) == 1
    assert skips(session) == [
        "СИСТЕМА · Real не открыт: NFLX mode_c — ошибка: RuntimeError: брокер недоступен"
    ]


def test_real_after_entry_window_is_refused(session: Session, event: orm.Event) -> None:
    go_live(session)
    record_cash(session, "deposit", Decimal("10000"), None, NOW)
    late = datetime(2026, 10, 21, 15, 30, tzinfo=UTC)  # 11:30 ET — лимит входа до 11:00
    run_decision(
        session,
        job(event.id, "mode_c_decision", "T0"),
        ["mode_c"],
        mode_c(),
        config=CONFIG,
        now=late,
        orders=orders(session),
    )
    assert real_cards(session) == []
    assert skips(session) == [
        "СИСТЕМА · Real не открыт: NFLX mode_c — окно входа до 11:00 ET прошло"
    ]


def test_stage_without_weight_uses_live_small_weight(session: Session, event: orm.Event) -> None:
    row = session.get(orm.Plugin, ("mode_c", "0.1.0"))
    assert row is not None
    row.stage, row.weight = "live_small", None  # новая версия из registry.yaml без promote
    session.flush()
    record_cash(session, "deposit", Decimal("10000"), None, NOW)
    run(session, event)
    assert real_cards(session) == []  # × 0,05, а не полный размер
    assert skips(session)[0].endswith("риск $2.50 меньше одной единицы ($4.04)")


def test_orange_level_blocks_real_without_model(session: Session, event: orm.Event) -> None:
    go_live(session)
    record_cash(session, "deposit", Decimal("10000"), None, NOW)
    session.add(orm.MarketLevelDay(day=date(2026, 10, 16), level="orange", vix=26.0, spy=500.0))
    session.flush()
    run(session, event)  # решение 19.10 — уровень закрытия 16.10
    assert real_cards(session) == []
    assert skips(session) == ["СИСТЕМА · Real не открыт: NFLX mode_c — отказ: MACRO_BLOCK"]
    paper = session.scalars(select(orm.TradeCard).where(orm.TradeCard.paper.is_(True))).all()
    assert len(paper) == 1  # paper уровень не режет — сбор данных


def test_short_plan_stop_above_entry() -> None:
    plan = stock_plan("NFLX", -1, 100.0, 4.0, 0.01)
    entry, stop = plan.orders
    assert (entry.side, entry.limit_price, stop.side, stop.stop_price) == (
        "sell",
        100.0,
        "buy",
        104.0,
    )
    assert round(plan.unit_risk, 2) == 4.04
