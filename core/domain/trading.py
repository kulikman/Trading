"""Решение по событию и карточка сделки (SPEC §5, §10, §11)."""

from decimal import Decimal
from typing import Any, Self

from pydantic import AwareDatetime, Field, model_validator

from core.domain.base import DomainModel
from core.domain.types import CardState, DecisionStatus, SkipReason

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


class TradeCard(DomainModel):
    id: int | None = None
    decision_id: int
    state: CardState
    paper: bool = True
    # TODO(T17): типизировать ноги, стоп и исполнения, когда появится исполнитель.
    legs: list[dict[str, Any]] = Field(min_length=1)
    stop: dict[str, Any] | None = None
    trailing: dict[str, Any] | None = None
    fills: list[dict[str, Any]] | None = None
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
