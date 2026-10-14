"""Ордер, котировка, позиция, исполнение — общий язык всех брокеров (SPEC §6)."""

from datetime import date
from typing import Literal, NewType, Self

from pydantic import AwareDatetime, Field, model_validator

from core.domain.base import DomainModel

OrderId = NewType("OrderId", str)
Side = Literal["buy", "sell"]
Instrument = Literal["stock", "option"]
OrderType = Literal["market", "limit", "stop"]
OptionRight = Literal["call", "put"]
# stop_gap — закрытие на открытии по стоп-гэпу: единственный рыночный ордер в первые минуты (§1).
OrderPurpose = Literal["entry", "exit", "stop", "stop_gap"]


class OptionSpec(DomainModel):
    underlying: str
    expiry: date
    strike: float = Field(gt=0)
    right: OptionRight


class Order(DomainModel):
    """client_order_id — ключ идемпотентности: повтор с тем же ключом не создаёт второй ордер."""

    client_order_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    instrument: Instrument
    side: Side
    quantity: int = Field(gt=0)  # акции или контракты
    multiplier: int = Field(gt=0)  # 1 для акций, размер контракта для опционов
    order_type: OrderType
    purpose: OrderPurpose
    limit_price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)
    option: OptionSpec | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.order_type == "limit" and self.limit_price is None:
            raise ValueError("limit order needs limit_price")
        if self.order_type == "stop" and self.stop_price is None:
            raise ValueError("stop order needs stop_price")
        if self.order_type == "market" and (self.limit_price or self.stop_price):
            raise ValueError("market order takes no limit_price or stop_price")
        if self.instrument == "option" and self.option is None:
            raise ValueError("option order needs option spec")
        if self.instrument == "stock" and (self.option is not None or self.multiplier != 1):
            raise ValueError("stock order has multiplier 1 and no option spec")
        return self


class Quote(DomainModel):
    symbol: str
    bid: float = Field(gt=0)
    ask: float = Field(gt=0)
    at: AwareDatetime

    @model_validator(mode="after")
    def _not_crossed(self) -> Self:
        if self.ask < self.bid:
            raise ValueError("ask below bid")
        return self

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2


class Fill(DomainModel):
    order_id: str
    client_order_id: str
    symbol: str
    instrument: Instrument
    side: Side
    quantity: int = Field(gt=0)
    multiplier: int = Field(gt=0)
    price: float = Field(gt=0)
    at: AwareDatetime


class Position(DomainModel):
    symbol: str
    instrument: Instrument
    quantity: int  # > 0 — длинная, < 0 — короткая
    multiplier: int = Field(gt=0)
    average_price: float = Field(gt=0)
