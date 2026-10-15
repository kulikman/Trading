"""Хранилище ордеров ManualBroker (T17): в памяти (тесты) или в таблице broker_order.

Ключ идемпотентности — client_order_id: повтор события находит существующий ордер.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import models as orm
from core.domain.broker import Fill, Order, OrderId

PendingStatus = Literal["pending", "filled", "cancelled"]


@dataclass
class Ticket:
    order_id: OrderId
    order: Order
    instruction: str
    status: PendingStatus = "pending"
    fill: Fill | None = None
    card_id: int | None = None


class OrderStore(Protocol):
    def by_client_id(self, client_order_id: str) -> Ticket | None:
        """Ордер по ключу идемпотентности."""

    def get(self, order_id: OrderId) -> Ticket | None:
        """Ордер по id."""

    def save(self, ticket: Ticket) -> None:
        """Записать новый или изменённый ордер."""

    def all(self) -> list[Ticket]:
        """Все ордера."""


class MemoryOrderStore:
    def __init__(self) -> None:
        self._tickets: dict[OrderId, Ticket] = {}

    def by_client_id(self, client_order_id: str) -> Ticket | None:
        return next(
            (t for t in self._tickets.values() if t.order.client_order_id == client_order_id), None
        )

    def get(self, order_id: OrderId) -> Ticket | None:
        return self._tickets.get(order_id)

    def save(self, ticket: Ticket) -> None:
        self._tickets[ticket.order_id] = ticket

    def all(self) -> list[Ticket]:
        return list(self._tickets.values())


class DbOrderStore:
    """broker_order; каждая запись — своя транзакция (подтверждение исполнения не теряется)."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session = session_factory

    def by_client_id(self, client_order_id: str) -> Ticket | None:
        with self._session() as session:
            row = session.scalars(
                select(orm.BrokerOrder).where(orm.BrokerOrder.client_order_id == client_order_id)
            ).first()
            return None if row is None else _ticket(row)

    def get(self, order_id: OrderId) -> Ticket | None:
        with self._session() as session:
            row = session.get(orm.BrokerOrder, order_id)
            return None if row is None else _ticket(row)

    def save(self, ticket: Ticket) -> None:
        with self._session() as session, session.begin():
            row = session.get(orm.BrokerOrder, ticket.order_id) or orm.BrokerOrder(
                order_id=ticket.order_id, client_order_id=ticket.order.client_order_id
            )
            row.card_id = ticket.card_id
            row.payload = ticket.order.model_dump(mode="json")
            row.instruction = ticket.instruction
            row.status = ticket.status
            row.fill = None if ticket.fill is None else ticket.fill.model_dump(mode="json")
            session.add(row)

    def all(self) -> list[Ticket]:
        with self._session() as session:
            return [_ticket(r) for r in session.scalars(select(orm.BrokerOrder))]


def _ticket(row: orm.BrokerOrder) -> Ticket:
    status: PendingStatus = (
        "filled"
        if row.status == "filled"
        else "cancelled"
        if row.status == "cancelled"
        else "pending"
    )
    return Ticket(
        order_id=OrderId(row.order_id),
        order=Order.model_validate(row.payload, strict=False),
        instruction=row.instruction,
        status=status,
        fill=None if row.fill is None else Fill.model_validate(row.fill, strict=False),
        card_id=row.card_id,
    )
