"""Издержки сделки (SPEC §17 п.3): комиссия, половина спреда, проскальзывание на открытии.

Обязательны в Paper, теневых сделках, бэктесте и в пороге edge > costs + 0.03 (CLAUDE.md правило 8).
У каждого брокера своя модель — параметры в config/broker.yaml.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from adapters.errors import DataError
from core.config.broker import CostSettings
from core.domain.broker import Instrument

SOURCE = "costs"


@dataclass(frozen=True)
class CostLeg:
    """Одна нога сделки на одной стороне (вход или выход). quantity — акции или контракты."""

    instrument: Instrument
    quantity: int
    multiplier: int
    price: float  # опорная цена: лимит или теоретическая
    bid: float | None = None
    ask: float | None = None


@dataclass(frozen=True)
class CostBreakdown:
    commission: float
    spread: float
    slippage: float
    spread_assumed: bool  # спред не из котировки, а из допущения конфигурации

    @property
    def total(self) -> float:
        return self.commission + self.spread + self.slippage

    def __add__(self, other: "CostBreakdown") -> "CostBreakdown":
        return CostBreakdown(
            self.commission + other.commission,
            self.spread + other.spread,
            self.slippage + other.slippage,
            self.spread_assumed or other.spread_assumed,
        )


ZERO = CostBreakdown(0.0, 0.0, 0.0, False)


class CostModel(Protocol):
    def leg_cost(self, leg: CostLeg, *, at_open: bool) -> CostBreakdown:
        """Издержки одной ноги на одной стороне, в долларах."""


class BrokerCostModel:
    """Линейная модель издержек брокера; все ставки — из конфига."""

    def __init__(self, settings: CostSettings) -> None:
        self._s = settings

    def leg_cost(self, leg: CostLeg, *, at_open: bool) -> CostBreakdown:
        units = leg.quantity * leg.multiplier
        commission = self._commission(leg)
        half_spread, assumed = self._half_spread(leg)
        mid = (leg.bid + leg.ask) / 2 if leg.bid is not None and leg.ask is not None else leg.price
        slippage = mid * self._s.open_slippage * units if at_open else 0.0
        return CostBreakdown(commission, half_spread * units, slippage, assumed)

    def _commission(self, leg: CostLeg) -> float:
        if leg.instrument == "option":
            return max(
                leg.quantity * self._s.commission_per_contract,
                self._s.min_commission_per_option_order,
            )
        commission = max(
            leg.quantity * self._s.commission_per_share, self._s.min_commission_per_stock_order
        )
        cap = self._s.max_commission_stock_fraction
        if cap is not None:
            commission = min(commission, cap * leg.quantity * leg.price)
        return commission

    def _half_spread(self, leg: CostLeg) -> tuple[float, bool]:
        if leg.bid is not None and leg.ask is not None:
            return (leg.ask - leg.bid) / 2, False
        assumed = (
            self._s.assumed_spread_stock
            if leg.instrument == "stock"
            else self._s.assumed_spread_option
        )
        if assumed is None:
            raise DataError(SOURCE, f"no {leg.instrument} quote and no assumed spread in config")
        return leg.price * assumed / 2, True


def total_cost(model: CostModel, legs: Iterable[CostLeg], *, at_open: bool) -> CostBreakdown:
    """Сумма издержек по ногам одной стороны сделки."""
    result = ZERO
    for leg in legs:
        result = result + model.leg_cost(leg, at_open=at_open)
    return result
