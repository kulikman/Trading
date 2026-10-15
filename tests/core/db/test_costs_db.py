from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.broker.manual import ManualBroker
from adapters.broker.order_store import DbOrderStore
from core.db import models as orm
from core.domain.broker import Order, Quote
from core.session_guard import ET
from execution.costs import CostBreakdown, CostLeg
from learning.costs import DRIFT_CODE, check_costs, real_executions

MIDDAY = datetime(2026, 10, 13, 12, 0, tzinfo=ET)
NOW = datetime(2026, 10, 13, 22, 30, tzinfo=UTC)


class HalfSpread:
    def leg_cost(self, leg: CostLeg, *, at_open: bool) -> CostBreakdown:
        return CostBreakdown(1.0, 0.05 * leg.quantity * leg.multiplier, 0.0, True)


def broker(session: Session) -> ManualBroker:
    store = DbOrderStore(
        lambda: Session(bind=session.connection(), join_transaction_mode="create_savepoint")
    )
    return ManualBroker(
        quote_source=lambda s: Quote(symbol=s, bid=99.9, ask=100.1, at=MIDDAY),
        no_market_orders_first_minutes=5,
        clock=lambda: MIDDAY,
        store=store,
    )


def place(manual: ManualBroker, n: int, price: float) -> None:
    order = Order(
        client_order_id=f"card-{n}-leg-1",
        symbol="GS",
        instrument="stock",
        side="buy",
        quantity=10,
        multiplier=1,
        order_type="limit",
        purpose="entry",
        limit_price=100.0,
    )
    manual.confirm_fill(manual.place(order), price=price, at=MIDDAY)


def test_button_confirmation_at_limit_is_not_a_measurement(session: Session) -> None:
    manual = broker(session)
    place(manual, 1, 100.0)  # «Исполнено» кнопкой — по цене лимита
    place(manual, 2, 100.1)
    assert [e.fill.price for e in real_executions(session)] == [100.1]


def test_drift_writes_one_system_message(session: Session) -> None:
    manual = broker(session)
    place(manual, 1, 100.1)
    place(manual, 2, 100.1)
    for _ in range(2):  # повтор вечернего прогона не дублирует сообщение
        result = check_costs(session, HalfSpread(), alert=0.2, min_fills=2, now=NOW)
        session.flush()
    assert result.drift
    texts = session.scalars(
        select(orm.SystemMessage.text).where(orm.SystemMessage.code == DRIFT_CODE)
    ).all()
    assert texts == [
        "СИСТЕМА · издержки Paper против реальности — расхождение 100% (2 исполнений), "
        "порог 20%. Пересчитать CostModel: допущение спреда × 2.00 (config/broker.yaml)"
    ]


def test_no_drift_no_message(session: Session) -> None:
    place(broker(session), 1, 100.1)
    result = check_costs(session, HalfSpread(), alert=0.2, min_fills=2, now=NOW)
    assert not result.drift
    assert session.scalars(select(orm.SystemMessage)).all() == []
