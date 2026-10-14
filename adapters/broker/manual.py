"""ManualBroker (MVP, SPEC §6): ничего не отправляет — формирует инструкцию для карточки.

Человек ставит ордер у брокера сам и жмёт «Исполнено» в Telegram → confirm_fill().
Состояние в памяти процесса; хранение в БД — вместе с машиной состояний (T17).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from adapters.broker.base import GuardedBroker, utc_now
from core.domain.broker import Fill, Order, OrderId, Position, Quote

PendingStatus = Literal["pending", "filled", "cancelled"]
SIDE_WORD = {"buy": "Купить", "sell": "Продать"}
LIMIT_SIGN = {"buy": "≤", "sell": "≥"}


class UnknownOrderError(KeyError):
    """Ордера с таким id нет."""


class OrderNotPendingError(Exception):
    """Ордер уже отменён (подтвердить исполнение нельзя)."""


@dataclass
class _Ticket:
    order_id: OrderId
    order: Order
    instruction: str
    status: PendingStatus = "pending"
    fill: Fill | None = None


def instruction_line(order: Order) -> str:
    """Строка карточки: «Купить  PUT 850 16.10  1 шт.  лимит ≤ 6.50» (SPEC §12)."""
    if order.option is not None:
        spec = order.option
        name = f"{spec.right.upper()} {spec.strike:g} {spec.expiry:%d.%m}"
    else:
        name = order.symbol
    head = f"{SIDE_WORD[order.side]}  {name}  {order.quantity} шт."
    if order.order_type == "limit" and order.limit_price is not None:
        return f"{head}  лимит {LIMIT_SIGN[order.side]} {order.limit_price:.2f}"
    if order.order_type == "stop" and order.stop_price is not None:
        return f"{head}  стоп {order.stop_price:.2f} (только основная сессия)"
    return f"{head}  по рынку"


class ManualBroker(GuardedBroker):
    def __init__(
        self,
        *,
        quote_source: Callable[[str], Quote],
        no_market_orders_first_minutes: int,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        super().__init__(no_market_orders_first_minutes=no_market_orders_first_minutes, clock=clock)
        self._quote_source = quote_source
        self._tickets: dict[OrderId, _Ticket] = {}
        self._by_client_id: dict[str, OrderId] = {}

    def _submit(self, order: Order) -> OrderId:
        existing = self._by_client_id.get(order.client_order_id)
        if existing is not None:
            return existing  # идемпотентность: повтор события не создаёт второй ордер
        order_id = OrderId(f"manual-{order.client_order_id}")
        self._tickets[order_id] = _Ticket(order_id, order, instruction_line(order))
        self._by_client_id[order.client_order_id] = order_id
        return order_id

    def instruction(self, order_id: OrderId) -> str:
        """Текст для карточки Telegram."""
        return self._ticket(order_id).instruction

    def quote(self, symbol: str) -> Quote:
        """В MVP — последний снимок рынка (SPEC §6, сверка цены)."""
        return self._quote_source(symbol)

    def cancel(self, order_id: OrderId) -> None:
        ticket = self._ticket(order_id)
        if ticket.status == "pending":
            ticket.status = "cancelled"

    def confirm_fill(self, order_id: OrderId, *, price: float, at: datetime) -> Fill:
        """Кнопка «Исполнено». Повторное нажатие возвращает то же исполнение."""
        ticket = self._ticket(order_id)
        if ticket.fill is not None:
            return ticket.fill
        if ticket.status == "cancelled":
            raise OrderNotPendingError(f"{order_id} is cancelled")
        order = ticket.order
        ticket.fill = Fill(
            order_id=order_id,
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            instrument=order.instrument,
            side=order.side,
            quantity=order.quantity,
            multiplier=order.multiplier,
            price=price,
            at=at,
        )
        ticket.status = "filled"
        return ticket.fill

    def fills(self, since: datetime) -> list[Fill]:
        return sorted(
            (t.fill for t in self._tickets.values() if t.fill is not None and t.fill.at >= since),
            key=lambda fill: fill.at,
        )

    def positions(self) -> list[Position]:
        """Позиции по подтверждённым исполнениям; средняя цена — по наращивающим сделкам."""
        book: dict[
            str, tuple[Fill, int, float]
        ] = {}  # символ → (пример, кол-во, стоимость открытия)
        for fill in sorted((t.fill for t in self._tickets.values() if t.fill), key=lambda f: f.at):
            signed = fill.quantity if fill.side == "buy" else -fill.quantity
            sample, quantity, cost = book.get(fill.symbol, (fill, 0, 0.0))
            if quantity == 0 or (quantity > 0) == (signed > 0):
                cost += abs(signed) * fill.price
            else:
                cost *= max(abs(quantity) - abs(signed), 0) / abs(quantity)
            book[fill.symbol] = (sample, quantity + signed, cost)
        return [
            Position(
                symbol=symbol,
                instrument=sample.instrument,
                quantity=quantity,
                multiplier=sample.multiplier,
                average_price=cost / abs(quantity),
            )
            for symbol, (sample, quantity, cost) in book.items()
            if quantity != 0
        ]

    def _ticket(self, order_id: OrderId) -> _Ticket:
        try:
            return self._tickets[order_id]
        except KeyError as exc:
            raise UnknownOrderError(order_id) from exc
