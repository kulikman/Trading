"""Интерфейс брокера (SPEC §6) и общая проверка «можно ли сейчас ставить этот ордер» (SPEC §1).

Код вне adapters/broker/ знает только BrokerAdapter (CLAUDE.md правило 7).
"""

from abc import ABC, abstractmethod
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Protocol

from core.domain.broker import Fill, Order, OrderId, Position, Quote
from core.session_guard import is_regular_session, session, to_et


class OrderRejectedError(Exception):
    """Ордер нельзя ставить сейчас. Ничего не отправлено."""


class OutsideSessionError(OrderRejectedError):
    """Вне основной сессии NYSE (9:30 — закрытие ET)."""


class MarketOrderTooEarlyError(OrderRejectedError):
    """Рыночный ордер в первые минуты после открытия (разрешён только стоп-гэп)."""


class BrokerAdapter(Protocol):
    def quote(self, symbol: str) -> Quote:
        """Текущая котировка."""

    def place(self, order: Order) -> OrderId:
        """Поставить ордер. Только в основную сессию (outside_rth=False у реальных брокеров)."""

    def cancel(self, order_id: OrderId) -> None:
        """Отменить ордер."""

    def positions(self) -> list[Position]:
        """Открытые позиции."""

    def fills(self, since: datetime) -> list[Fill]:
        """Исполнения с момента since."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def check_order_allowed(order: Order, now: datetime, no_market_orders_first_minutes: int) -> None:
    """Сессия открыта; рыночный ордер — не раньше N минут после открытия (кроме стоп-гэпа)."""
    if not is_regular_session(now):
        raise OutsideSessionError(
            f"{order.client_order_id}: regular session is closed at {now.isoformat()}"
        )
    if order.order_type != "market" or order.purpose == "stop_gap":
        return
    today = session(to_et(now).date())
    if today is not None and now < today.open + timedelta(minutes=no_market_orders_first_minutes):
        raise MarketOrderTooEarlyError(
            f"{order.client_order_id}: no market orders in the first "
            f"{no_market_orders_first_minutes} minutes after the open"
        )


class GuardedBroker(ABC):
    """База реализаций: place() всегда проходит check_order_allowed, затем _submit()."""

    def __init__(
        self, *, no_market_orders_first_minutes: int, clock: Callable[[], datetime] = utc_now
    ) -> None:
        self._no_market_minutes = no_market_orders_first_minutes
        self._clock = clock

    def place(self, order: Order) -> OrderId:
        check_order_allowed(order, self._clock(), self._no_market_minutes)
        return self._submit(order)

    @abstractmethod
    def _submit(self, order: Order) -> OrderId:
        """Отправка у конкретного брокера (после проверок)."""

    @abstractmethod
    def quote(self, symbol: str) -> Quote:
        """Текущая котировка."""

    @abstractmethod
    def cancel(self, order_id: OrderId) -> None:
        """Отменить ордер."""

    @abstractmethod
    def positions(self) -> list[Position]:
        """Открытые позиции."""

    @abstractmethod
    def fills(self, since: datetime) -> list[Fill]:
        """Исполнения с момента since."""
