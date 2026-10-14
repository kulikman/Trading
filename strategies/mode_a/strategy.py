"""Режим A (SPEC §10, T16): вход T−7 в длинную акцию, стоп 1,5 × ATR(14), выход T−1 15:50.

Условия: pre_run_30d < +10%, VIX < 25, тренд сектора ≥ 0. Рост за 3 дня (SPEC §10): +3…+6% —
A нет; > +6% — PRE_RUN; ≤ −4% — A на отскок (разрешён). Edge = p_up − рыночный p_up.
Стартовая стадия — shadow до бэктеста (SPEC §17 п.4).
"""

from core.domain.types import SkipReason
from core.registry.protocols import DecisionContext, Proposal, Skip
from core.session_guard import to_et
from strategies.base import StrategyBase, as_reasons
from strategies.common import stock_cost_fraction, stock_state


class ModeAStrategy(StrategyBase):
    id = "mode_a"
    version = "0.1.0"
    mode = "A"

    def evaluate(self, ctx: DecisionContext) -> Proposal | Skip:
        rules, pre_run = self._thresholds.modes.A, self._thresholds.pre_run_3d
        positioning, macro = ctx.features.get("positioning", {}), ctx.features.get("macro", {})
        sector, forecasts = ctx.features.get("sector", {}), ctx.forecasts
        if "p_up" not in forecasts or "market_p_up" not in forecasts:
            return self.skip("DATA_MASSIVE")
        reasons: list[SkipReason] = []
        run_30d, run_3d = positioning.get("pre_run_30d"), positioning.get("pre_run_3d")
        if run_30d is not None and run_30d >= rules.max_pre_run_30d:
            reasons.append("PRE_RUN")
        if run_3d is not None and run_3d >= pre_run.neutral_below:
            reasons.append("PRE_RUN")  # +3…+6% — A нет, > +6% — PRE_RUN
        vix = macro.get("vix")
        if vix is not None and vix >= rules.max_vix:
            reasons.append("MACRO_BLOCK")
        trend = sector.get("trend")
        if trend is not None and trend < rules.min_sector_trend:
            reasons.append("PEER_CONFLICT")
        if reasons:
            return self.skip(*as_reasons(reasons))
        day = to_et(ctx.event.as_of).date()
        state = stock_state(self._stocks, ctx.event.ticker, day, rules.atr_period)
        cost = (
            None
            if state is None or state.atr is None
            else stock_cost_fraction(self._costs, state.spot, rules.stop_atr_multiple * state.atr)
        )
        if cost is None:
            return self.skip("DATA_MASSIVE")
        p = forecasts["p_up"]
        return Proposal(
            strategy_id=self.id,
            mode=self.mode,
            construction="stock",
            edge=p - forecasts["market_p_up"],
            confidence=p,
            probability=p,
            cost_fraction=cost,
        )
