"""Базовые части стратегий-плагинов (T16): зависимости, сессия, пропуск с кодами."""

from collections.abc import Sequence

from sqlalchemy.orm import Session

from adapters.massive.symbols import StockHistorySource
from core.config import AppConfig
from core.config.thresholds import Thresholds
from core.domain.trading import TradeCard
from core.domain.types import SkipReason
from core.registry.protocols import Action, DecisionContext, MarketState, Skip
from execution.costs import BrokerCostModel, CostModel


class StrategyBase:
    """Общее для стратегий: пороги, модель издержек, цены акций; выходы — исполнитель (T17)."""

    id: str
    version: str
    mode: str

    def __init__(
        self,
        stocks: StockHistorySource,
        costs: CostModel,
        thresholds: Thresholds,
        rate: float,
    ) -> None:
        self._stocks = stocks
        self._costs = costs
        self._thresholds = thresholds
        self._rate = (
            rate  # ставка для оценки цен опционов в издержках (допущение history.risk_free_rate)
        )

    def skip(self, *reasons: SkipReason) -> Skip:
        return Skip(self.id, list(reasons))

    def exit_rules(self, card: TradeCard, market: MarketState) -> list[Action]:
        """Правила выхода исполняет машина состояний карточки (T17)."""
        return []


def session_of(ctx: DecisionContext) -> Session:
    if ctx.event.session is None:
        raise ValueError("decision context has no archive session")
    return ctx.event.session


def dependencies(config: AppConfig) -> tuple[CostModel, float]:
    """Модель издержек выбранного брокера и ставка для цен опционов."""
    broker = config.broker
    return BrokerCostModel(
        broker.costs[broker.broker]
    ), config.sources.massive.history.risk_free_rate


def as_reasons(reasons: Sequence[SkipReason]) -> list[SkipReason]:
    return list(dict.fromkeys(reasons))
