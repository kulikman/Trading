from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.broker.manual import ManualBroker, OrderNotPendingError
from adapters.broker.order_store import DbOrderStore
from core.db import models as orm
from core.domain.broker import OptionSpec, Order, Quote
from core.session_guard import ET

MIDDAY = datetime(2026, 10, 13, 12, 0, tzinfo=ET)


def broker(session: Session) -> ManualBroker:
    store = DbOrderStore(
        lambda: Session(bind=session.connection(), join_transaction_mode="create_savepoint")
    )
    return ManualBroker(
        quote_source=lambda s: Quote(symbol=s, bid=1, ask=1.1, at=MIDDAY),
        no_market_orders_first_minutes=5,
        clock=lambda: MIDDAY,
        store=store,
    )


def order(client_id: str = "card-7-leg-1") -> Order:
    return Order(
        client_order_id=client_id,
        symbol="GS261016P00850000",
        instrument="option",
        side="buy",
        quantity=1,
        multiplier=100,
        order_type="limit",
        purpose="entry",
        limit_price=6.5,
        option=OptionSpec(underlying="GS", expiry=date(2026, 10, 16), strike=850, right="put"),
    )


def test_orders_survive_restart_and_repeat_is_idempotent(session: Session) -> None:
    first = broker(session)
    order_id = first.place(order())
    assert first.place(order()) == order_id  # повтор события — тот же ордер
    assert session.scalars(select(orm.BrokerOrder)).one().instruction == (
        "Купить  PUT 850 16.10  1 шт.  лимит ≤ 6.50"
    )
    restarted = broker(session)  # новый процесс — ордер из базы
    fill = restarted.confirm_fill(order_id, price=6.4, at=MIDDAY)
    assert restarted.confirm_fill(order_id, price=9.9, at=MIDDAY) == fill  # повторное нажатие
    row = session.scalars(select(orm.BrokerOrder)).one()
    assert row.status == "filled"
    assert (row.fill or {})["price"] == 6.4
    assert [p.symbol for p in broker(session).positions()] == ["GS261016P00850000"]
    assert broker(session).fills(MIDDAY) == [fill]


def test_cancelled_order_cannot_be_filled(session: Session) -> None:
    b = broker(session)
    order_id = b.place(order("card-8-leg-1"))
    b.cancel(order_id)
    assert session.scalars(select(orm.BrokerOrder.status)).one() == "cancelled"
    with pytest.raises(OrderNotPendingError):
        broker(session).confirm_fill(order_id, price=6.0, at=MIDDAY)
