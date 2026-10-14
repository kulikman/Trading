"""Модель config/broker.yaml: выбранный брокер и модель издержек каждого брокера (SPEC §17 п.5)."""

from typing import Literal, Self

from pydantic import Field, model_validator

from core.config.base import Fraction, StrictModel

BrokerName = Literal["manual", "ib", "freedom"]


class CostSettings(StrictModel):
    commission_per_share: float = Field(ge=0)
    min_commission_per_stock_order: float = Field(ge=0)
    max_commission_stock_fraction: Fraction | None  # потолок комиссии как доля суммы сделки
    commission_per_contract: float = Field(ge=0)
    min_commission_per_option_order: float = Field(ge=0)
    open_slippage: Fraction
    assumed_spread_stock: Fraction | None  # None — без котировки спред неизвестен → DataError
    assumed_spread_option: Fraction | None


class BrokerConfig(StrictModel):
    broker: BrokerName
    costs: dict[BrokerName, CostSettings]

    @model_validator(mode="after")
    def _selected_has_costs(self) -> Self:
        if self.broker not in self.costs:
            raise ValueError(f"no cost model for selected broker {self.broker}")
        return self

    @property
    def selected_costs(self) -> CostSettings:
        return self.costs[self.broker]
