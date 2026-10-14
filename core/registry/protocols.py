"""Протоколы плагинов (SPEC §7): агенты пишут признаки, стратегии предлагают сделки.

Контексты минимальные — только поля из SPEC и схемы БД; агенты (T14) и решение (T16)
дополняют их, не меняя подписи методов.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, Protocol

from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.domain.trading import TradeCard
from core.domain.types import FeatureStage, ReportTime, SkipReason

TriggerKind = Literal["stage", "event"]


@dataclass(frozen=True)
class Trigger:
    """Когда запускать агента: на стадии события (T−7, T−3…) или по событию системы."""

    kind: TriggerKind
    value: str  # стадия «T-7» или имя события («report_published»)


@dataclass(frozen=True)
class EventContext:
    """Что агент знает о событии на момент запуска."""

    event_id: int
    ticker: str
    report_date: date
    report_time: ReportTime | None
    stage: FeatureStage
    as_of: datetime
    session: Session | None = None  # архив (только чтение) — агентам, которым нужна история


@dataclass(frozen=True)
class DecisionContext:
    """Что стратегия видит при решении: признаки агентов, влияющих на решение (не shadow)."""

    event: EventContext
    features: Mapping[str, Mapping[str, float]]  # agent_id → признаки
    forecasts: Mapping[str, float] = field(default_factory=dict)  # p_beat, p_up, move_ratio…


@dataclass(frozen=True)
class Proposal:
    """Предложение сделки; размер и лимиты режет Capital Manager (T16)."""

    strategy_id: str
    mode: str
    construction: str
    edge: float
    confidence: float


@dataclass(frozen=True)
class Skip:
    strategy_id: str
    reasons: Sequence[SkipReason]


@dataclass(frozen=True)
class MarketState:
    as_of: datetime
    prices: Mapping[str, float]  # тикер / контракт → цена


@dataclass(frozen=True)
class Action:
    kind: Literal["close", "move_stop", "hold"]
    reason: str


class Agent(Protocol):
    id: str
    version: str
    triggers: Sequence[Trigger]
    reads: Sequence[str]  # какие данные нужны
    output_schema: type[BaseModel]  # только числовые поля + необязательный текст для человека

    def run(self, ctx: EventContext) -> BaseModel:
        """Признаки агента для события."""


class Strategy(Protocol):
    id: str
    version: str
    mode: str  # 'A' | 'B' | 'C' | новый

    def evaluate(self, ctx: DecisionContext) -> Proposal | Skip:
        """Предложение сделки или пропуск с кодами."""

    def exit_rules(self, card: TradeCard, market: MarketState) -> list[Action]:
        """Действия по открытой позиции."""
