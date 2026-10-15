"""Решение по событию и карточка сделки (SPEC §5, §10, §11)."""

from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import AwareDatetime, Field, model_validator

from core.domain.base import DomainModel
from core.domain.broker import Instrument, OrderPurpose, Side
from core.domain.types import CardState, DecisionStatus, OrderStatus, SkipReason

DATA_REASON_PREFIX = "DATA_"


class Decision(DomainModel):
    """Итог события. reasons[0] — главная причина (SPEC §5)."""

    id: int | None = None
    event_id: int
    status: DecisionStatus
    reasons: list[SkipReason] = Field(default_factory=list)
    mode: str | None = None
    strategy_id: str | None = None
    construction: str | None = None
    shadow: dict[str, Any] | None = None
    decided_at: AwareDatetime

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.status in ("SKIPPED", "DATA_FAIL") and not self.reasons:
            raise ValueError(f"{self.status} decision needs at least one reason code")
        if self.status == "DATA_FAIL" and not self.reasons[0].startswith(DATA_REASON_PREFIX):
            raise ValueError("DATA_FAIL decision must have a DATA_* code as the main reason")
        if self.status == "ENTERED" and (self.strategy_id is None or self.construction is None):
            raise ValueError("ENTERED decision needs strategy_id and construction")
        return self


class CardLeg(DomainModel):
    """Нога позиции. У paper количество дробное: позиция — доля, дающая заданный риск."""

    symbol: str = Field(min_length=1)
    instrument: Instrument
    side: Side
    quantity: float = Field(gt=0)
    multiplier: int = Field(gt=0)


class CardFill(DomainModel):
    """Исполнение ноги: вход или выход (у paper — цена из архива по правилам конструкции)."""

    symbol: str = Field(min_length=1)
    side: Side
    quantity: float = Field(gt=0)
    price: float = Field(ge=0)
    at: AwareDatetime
    purpose: OrderPurpose


class CardStop(DomainModel):
    """Правило стопа позиции; price — уровень, если он один (акция)."""

    rule: str = Field(min_length=1)
    price: float | None = Field(default=None, gt=0)


class CardTrailing(DomainModel):
    """Трейлинг-стоп режима C: multiple × ATR, пересчёт после закрытия (SPEC §10)."""

    atr: float = Field(gt=0)
    multiple: float = Field(gt=0)
    stop: float = Field(gt=0)
    updated_at: AwareDatetime


class TradeCard(DomainModel):
    id: int | None = None
    decision_id: int
    state: CardState
    paper: bool = True
    legs: list[CardLeg] = Field(default_factory=list)  # пусто, пока не было входа
    stop: CardStop | None = None
    trailing: CardTrailing | None = None
    fills: list[CardFill] | None = None
    tg_message_id: int | None = None
    pnl_total: Decimal | None = None
    pnl_direction: Decimal | None = None
    pnl_vol: Decimal | None = None
    pnl_ivcrush: Decimal | None = None


class TradeCardTransition(DomainModel):
    id: int | None = None
    card_id: int
    at: AwareDatetime
    from_state: CardState | None = None
    to_state: CardState
    reason: str | None = None
    payload: dict[str, Any] | None = None


class BrokerOrderRecord(DomainModel):
    """Ордер ManualBroker (таблица broker_order, T17)."""

    order_id: str = Field(min_length=1)
    client_order_id: str = Field(min_length=1)
    card_id: int | None = None
    payload: dict[str, Any]
    instruction: str
    status: OrderStatus
    fill: dict[str, Any] | None = None


class CashMovement(DomainModel):
    """Пополнение (+) или вывод (−) счёта Real (таблица cash_movement, T17)."""

    id: int | None = None
    account: Literal["real"] = "real"
    at: AwareDatetime
    amount: Decimal
    note: str | None = None

    @model_validator(mode="after")
    def _nonzero(self) -> Self:
        if self.amount == 0:
            raise ValueError("cash movement amount must not be zero")
        return self


class SourceStatusRecord(DomainModel):
    """Источник данных (таблица source_status, T18)."""

    source: str = Field(min_length=1)
    last_ok_at: AwareDatetime | None = None
    last_error_at: AwareDatetime | None = None
    last_error: str | None = None


class SystemMessageRecord(DomainModel):
    """Сообщение «СИСТЕМА» (таблица system_message, T18)."""

    id: int | None = None
    at: AwareDatetime
    code: str | None = None
    text: str = Field(min_length=1)
    sent_at: AwareDatetime | None = None
    tg_message_id: int | None = None
