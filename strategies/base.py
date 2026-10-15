"""Базовые части стратегий-плагинов (T16): зависимости, сессия, пропуск с кодами."""

import logging
from collections.abc import Sequence
from datetime import date
from typing import Protocol

from sqlalchemy.orm import Session

from adapters.errors import DataError
from adapters.massive.models import OptionSnapshot
from adapters.massive.symbols import StockHistorySource
from core.config import AppConfig
from core.config.thresholds import Thresholds
from core.domain.trading import TradeCard
from core.domain.types import SkipReason
from core.registry.protocols import Action, DecisionContext, MarketState, Skip
from execution.costs import BrokerCostModel, CostModel
from strategies.options_plan import Contract, traded_contracts

logger = logging.getLogger(__name__)


class ChainSource(Protocol):
    def option_chain(
        self,
        underlying: str,
        *,
        expiration_gte: date | None = None,
        expiration_lte: date | None = None,
        strike_gte: float | None = None,
        strike_lte: float | None = None,
    ) -> list[OptionSnapshot]:
        """Снимок цепочки Massive."""


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
        chain: ChainSource | None = None,
    ) -> None:
        self._stocks = stocks
        self._chain = chain  # цепочка опционов для плана Real (E10-2b); нет — Real без плана
        self._costs = costs
        self._thresholds = thresholds
        self._rate = (
            rate  # ставка для оценки цен опционов в издержках (допущение history.risk_free_rate)
        )

    def options_contracts(
        self, ticker: str, expiration: date, day: date, spot: float, band: float
    ) -> list[Contract]:
        """Контракты экспирации со сделкой в день решения; сбой цепочки — пусто (paper цел)."""
        if self._chain is None:
            return []
        try:
            rows = self._chain.option_chain(
                ticker,
                expiration_gte=expiration,
                expiration_lte=expiration,
                strike_gte=spot * (1 - band),
                strike_lte=spot * (1 + band),
            )
        except DataError as exc:
            logger.warning(
                "chain for real plan unavailable", extra={"ticker": ticker, "detail": exc.detail}
            )
            return []
        return traded_contracts(rows, expiration, day)

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
