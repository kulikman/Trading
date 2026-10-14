"""Стрэддл (SPEC §10, T16): исторический ratio движения > straddle.min_move_ratio, вход T−1.

Edge = P(|движение| > implied move) модели − эталон рынка (частота из архива, решение заказчика
14.10.2026); уверенность и вероятность для Келли — та же P. Издержки — доля от премии.
"""

from core.registry.protocols import DecisionContext, Proposal, Skip
from core.session_guard import to_et
from strategies.base import StrategyBase, session_of
from strategies.common import history_ratio, stock_state, straddle_cost_fraction


class StraddleStrategy(StrategyBase):
    id = "straddle"
    version = "0.1.0"
    mode = "move"

    def evaluate(self, ctx: DecisionContext) -> Proposal | Skip:
        options, forecasts = ctx.features.get("options", {}), ctx.forecasts
        implied = options.get("implied_move")
        if implied is None or "move_ratio" not in forecasts or "market_move" not in forecasts:
            return self.skip("DATA_MASSIVE")
        backtest = self._thresholds.backtest
        ratio = history_ratio(
            session_of(ctx),
            ctx.event.ticker,
            ctx.event.report_date,
            implied,
            lookback=backtest.signal_lookback_reports,
            min_reports=backtest.signal_min_reports,
        )
        if ratio is None or ratio <= self._thresholds.constructions.straddle.min_move_ratio:
            return self.skip("EDGE_LOW")  # движения в прошлом не больше ожидаемого
        day = to_et(ctx.event.as_of).date()
        state = stock_state(
            self._stocks, ctx.event.ticker, day, self._thresholds.modes.C.atr_period
        )
        cost = None if state is None else straddle_cost_fraction(self._costs, state.spot, implied)
        if cost is None:
            return self.skip("DATA_MASSIVE")
        p = forecasts["move_ratio"]
        return Proposal(
            strategy_id=self.id,
            mode=self.mode,
            construction="straddle",
            edge=p - forecasts["market_move"],
            confidence=p,
            probability=p,
            cost_fraction=cost,
        )
