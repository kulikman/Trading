"""Режим C (SPEC §10, T16): акция после подтверждённого сюрприза, решение T0 10:45 ET.

Правила бэктеста T12b (решение заказчика 15.10.2026): сюрприз EPS по модулю > 5%, цена к 10:30
ушла от закрытия накануне в сторону сюрприза, объём первого часа > 2× среднего первого часа за
20 дней. Минутные данные приходят с задержкой 15 минут — к 10:45 первый час 09:30–10:30 уже есть.
Выручка и guidance не условие (записываются в earnings_track). Лимит входа — VWAP первого часа
± 0,3%, исполнение до 11:00 — исполнитель (T17); стоп — трейлинг 2 × ATR(14).
Модели у режима C нет: edge и уверенность 0, вход — по сигналу (сезоны 1–2, сбор данных).
"""

from sqlalchemy import select

from adapters.errors import DataError
from adapters.massive.symbols import symbol_on, symbol_periods
from backtest.mode_c import confirm, direction_of, entry_limit
from backtest.mode_c_run import StockData, previous_days
from core.config.thresholds import Thresholds
from core.db import models as orm
from core.domain.broker import Order, Side
from core.domain.trading import TradePlan
from core.registry.protocols import DecisionContext, Proposal, Skip
from core.session_guard import reaction_day, to_et
from decision.report import ReportSource, event_consensus, fetch_report_facts
from execution.costs import CostModel
from strategies.base import StrategyBase, session_of
from strategies.common import stock_cost_fraction, stock_state


class ModeCStrategy(StrategyBase):
    id = "mode_c"
    version = "0.1.0"
    mode = "C"

    def __init__(
        self,
        stocks: StockData,
        reports: ReportSource,
        costs: CostModel,
        thresholds: Thresholds,
        rate: float,
    ) -> None:
        super().__init__(stocks, costs, thresholds, rate)
        self._minutes = stocks
        self._reports = reports

    def evaluate(self, ctx: DecisionContext) -> Proposal | Skip:
        rules, settings = self._thresholds.modes.C, self._thresholds.backtest.mode_c
        event = ctx.event
        reaction = reaction_day(event.report_date, event.report_time)
        if to_et(event.as_of).date() != reaction:
            return self.skip("DATA_CALENDAR")  # решение режима C — только в день реакции
        try:
            surprise = self._surprise(ctx)
        except DataError:
            return self.skip("DATA_FINNHUB")
        if surprise is None:
            return self.skip("DATA_FINNHUB")  # отчёта или консенсуса в Finnhub ещё нет
        direction = direction_of(surprise, rules)
        if direction is None:
            return self.skip("C_NOT_CONFIRMED")
        state = stock_state(self._stocks, event.ticker, reaction, rules.atr_period)
        if state is None or state.atr is None:
            return self.skip("DATA_MASSIVE")
        history = previous_days(reaction, settings.volume_lookback_days)
        periods = symbol_periods(event.ticker, self._stocks.ticker_changes(event.ticker))
        minutes = self._minutes.aggregates(
            symbol_on(periods, reaction), 1, "minute", history[-1], reaction, adjusted=False
        )
        vwap = confirm(direction, state.spot, reaction, minutes, history, rules, settings)
        if vwap == "no_volume_history":
            return self.skip("DATA_MASSIVE")
        if isinstance(vwap, str):
            return self.skip("C_NOT_CONFIRMED")
        limit = entry_limit(direction, vwap, rules)
        stop_distance = rules.trailing_atr_multiple * state.atr
        cost = stock_cost_fraction(self._costs, limit, stop_distance)
        if cost is None:
            return self.skip("DATA_MASSIVE")
        return Proposal(
            strategy_id=self.id,
            mode=self.mode,
            construction="stock" if direction == 1 else "stock_short",
            edge=0.0,
            confidence=0.0,
            probability=0.0,
            cost_fraction=cost,
            plan=stock_plan(event.ticker, direction, limit, stop_distance, cost),
        )

    def _surprise(self, ctx: DecisionContext) -> float | None:
        """Сюрприз EPS из earnings_track (задача parse_report); нет — свежий запрос в Finnhub."""
        event = ctx.event
        stored = session_of(ctx).scalar(
            select(orm.EarningsTrack.eps_surprise_pct).where(
                orm.EarningsTrack.ticker == event.ticker,
                orm.EarningsTrack.report_date == event.report_date,
            )
        )
        if stored is not None:
            return stored
        consensus = event_consensus(
            session_of(ctx), event.ticker, event.report_date, event.report_time
        )
        facts = fetch_report_facts(self._reports, event.ticker, event.report_date, consensus)
        return None if facts is None else facts.eps_surprise_pct


def stock_plan(
    ticker: str, direction: int, limit: float, stop_distance: float, cost_fraction: float
) -> TradePlan:
    """Real на одну акцию: лимит входа до 11:00 и стоп на 2 × ATR от лимита (SPEC §10)."""
    entry_side: Side = "buy" if direction == 1 else "sell"
    exit_side: Side = "sell" if direction == 1 else "buy"
    stop = round(limit - direction * stop_distance, 2)
    return TradePlan(
        orders=(
            Order(
                client_order_id="plan-entry",
                symbol=ticker,
                instrument="stock",
                side=entry_side,
                quantity=1,
                multiplier=1,
                order_type="limit",
                purpose="entry",
                limit_price=round(limit, 2),
            ),
            Order(
                client_order_id="plan-stop",
                symbol=ticker,
                instrument="stock",
                side=exit_side,
                quantity=1,
                multiplier=1,
                order_type="stop",
                purpose="stop",
                stop_price=stop,
            ),
        ),
        unit_risk=stop_distance * (1 + cost_fraction),
        stop_rule=f"трейлинг 2 × ATR(14), старт {stop:.2f}",
    )
