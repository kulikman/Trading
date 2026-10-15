"""Iron condor (SPEC §10, T16): исторический ratio < iron_condor.max_move_ratio, вход T−1.

Выигрыш — движение не больше ожидаемого: вероятность = 1 − P(|движение| > implied move);
edge = эта вероятность − её рыночный эталон (частота из архива). Издержки — доля от
максимального убытка (ширина крыла − премия) при страйках ± short / wing implied move.
"""

from core.registry.protocols import DecisionContext, Proposal, Skip
from core.session_guard import to_et
from strategies.base import StrategyBase, session_of
from strategies.common import (
    condor_cost_fraction,
    front_expiration,
    history_ratio,
    stock_state,
    years_to,
)
from strategies.options_plan import STRIKE_BAND, condor_plan


class IronCondorStrategy(StrategyBase):
    id = "iron_condor"
    version = "0.1.0"
    mode = "move"

    def evaluate(self, ctx: DecisionContext) -> Proposal | Skip:
        options, forecasts = ctx.features.get("options", {}), ctx.forecasts
        implied, iv = options.get("implied_move"), options.get("atm_iv")
        if implied is None or iv is None or "move_ratio" not in forecasts:
            return self.skip("DATA_MASSIVE")
        if "market_move" not in forecasts:
            return self.skip("DATA_MASSIVE")
        backtest, condor = self._thresholds.backtest, self._thresholds.constructions.iron_condor
        ratio = history_ratio(
            session_of(ctx),
            ctx.event.ticker,
            ctx.event.report_date,
            implied,
            lookback=backtest.signal_lookback_reports,
            min_reports=backtest.signal_min_reports,
        )
        if ratio is None or ratio >= condor.max_move_ratio:
            return self.skip("EDGE_LOW")  # движения в прошлом не меньше ожидаемого
        day = to_et(ctx.event.as_of).date()
        state = stock_state(
            self._stocks, ctx.event.ticker, day, self._thresholds.modes.C.atr_period
        )
        if state is None:
            return self.skip("DATA_MASSIVE")
        expiration = front_expiration(ctx.event.report_date, ctx.event.report_time)
        cost = condor_cost_fraction(
            self._costs,
            state.spot,
            implied,
            iv,
            years_to(state.day, expiration),
            self._rate,
            condor.short_implied_moves,
            condor.wing_implied_moves,
        )
        if cost is None:
            return self.skip("DATA_MASSIVE")
        p = 1 - forecasts["move_ratio"]
        contracts = self.options_contracts(
            ctx.event.ticker, expiration, day, state.spot, STRIKE_BAND
        )
        return Proposal(
            strategy_id=self.id,
            mode=self.mode,
            construction="iron_condor",
            edge=p - (1 - forecasts["market_move"]),
            confidence=p,
            probability=p,
            cost_fraction=cost,
            plan=condor_plan(ctx.event.ticker, contracts, state.spot, implied, condor, self._costs),
        )
