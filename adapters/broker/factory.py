"""Единственное место, которое знает реализации брокеров (SPEC §17 п.5, CLAUDE.md правило 7).

Остальной код получает BrokerAdapter и CostModel отсюда: смена брокера — только config/broker.yaml.
"""

from collections.abc import Callable
from datetime import datetime

from adapters.broker.base import BrokerAdapter, GuardedBroker, utc_now
from adapters.broker.manual import ManualBroker
from adapters.broker.order_store import OrderStore
from adapters.broker.stubs import FreedomBroker, IbBroker
from core.config.broker import BrokerConfig
from core.domain.broker import Quote
from execution.costs import BrokerCostModel, CostModel


def create_broker(
    config: BrokerConfig,
    *,
    quote_source: Callable[[str], Quote],
    no_market_orders_first_minutes: int,
    clock: Callable[[], datetime] = utc_now,
    order_store: OrderStore | None = None,
) -> BrokerAdapter:
    """Брокер из config.broker; ManualBroker хранит ордера в order_store (в системе — БД)."""
    broker: GuardedBroker
    if config.broker == "manual":
        broker = ManualBroker(
            quote_source=quote_source,
            no_market_orders_first_minutes=no_market_orders_first_minutes,
            clock=clock,
            store=order_store,
        )
    elif config.broker == "ib":
        broker = IbBroker(
            no_market_orders_first_minutes=no_market_orders_first_minutes, clock=clock
        )
    else:
        broker = FreedomBroker(
            no_market_orders_first_minutes=no_market_orders_first_minutes, clock=clock
        )
    return broker


def create_cost_model(config: BrokerConfig) -> CostModel:
    """Модель издержек выбранного брокера."""
    return BrokerCostModel(config.selected_costs)
