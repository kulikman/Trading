"""Заглушки брокеров фазы 5 (T22): IB и Freedom (Tradernet). Любая операция — NotImplemented."""

from datetime import datetime

from adapters.broker.base import GuardedBroker
from core.domain.broker import Fill, Order, OrderId, Position, Quote


class _NotYetBroker(GuardedBroker):
    name = "broker"

    def _fail(self) -> NotImplementedError:
        return NotImplementedError(f"{self.name} adapter is phase 5 (TASKS T22)")

    def _submit(self, order: Order) -> OrderId:
        raise self._fail()

    def quote(self, symbol: str) -> Quote:
        raise self._fail()

    def cancel(self, order_id: OrderId) -> None:
        raise self._fail()

    def positions(self) -> list[Position]:
        raise self._fail()

    def fills(self, since: datetime) -> list[Fill]:
        raise self._fail()


class IbBroker(_NotYetBroker):
    name = "ib"


class FreedomBroker(_NotYetBroker):
    name = "freedom"
