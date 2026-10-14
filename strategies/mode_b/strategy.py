"""Режим B (SPEC §10, T16): ворота на T−3, решение на T−1, позиция через отчёт по направлению.

Направление — сторона, где модель сильнее рынка: рост при p_up ≥ рыночного, иначе падение.
Конструкция: рост — акция + коллар (пут −5%, колл +7–8%); падение — медвежий вертикальный
спред (пут у цены, проданный на 5% ниже). Ворота: уверенность ≥ θ_B (проверяет Chief Trader),
нет PEER_CONFLICT (тренд сектора против направления), нет PRE_RUN (> +6% за 3 дня без причины:
раскрытия компании или отчёта информатора за 14 дней); карантин компании — CALIBRATION.
Размер: +3…+6% за 3 дня — × 0,5; ≤ −4% и сигнал на рост — × 1,2. Стадия — shadow (SPEC §17).
"""

from datetime import timedelta

from sqlalchemy import select

from core.db import models as orm
from core.domain.types import SkipReason
from core.registry.protocols import DecisionContext, Proposal, Skip
from core.session_guard import to_et
from strategies.base import StrategyBase, as_reasons, session_of
from strategies.common import (
    collar_cost_fraction,
    front_expiration,
    put_spread_cost_fraction,
    stock_state,
    years_to,
)

INFORMANT_WINDOW_DAYS = 14  # отчёт информатора «недавно» — за две недели до решения


class ModeBStrategy(StrategyBase):
    id = "mode_b"
    version = "0.1.0"
    mode = "B"

    def evaluate(self, ctx: DecisionContext) -> Proposal | Skip:
        forecasts, options = ctx.forecasts, ctx.features.get("options", {})
        if "p_up" not in forecasts or "market_p_up" not in forecasts or "atm_iv" not in options:
            return self.skip("DATA_MASSIVE")
        p_up, market = forecasts["p_up"], forecasts["market_p_up"]
        direction = 1 if p_up >= market else -1
        p = p_up if direction > 0 else 1 - p_up
        reasons: list[SkipReason] = []
        trend = ctx.features.get("sector", {}).get("trend")
        if trend is not None and trend * direction < 0:
            reasons.append("PEER_CONFLICT")
        run_3d = ctx.features.get("positioning", {}).get("pre_run_3d")
        rules = self._thresholds.pre_run_3d
        if run_3d is not None and run_3d > rules.skip_above and not self._has_reason(ctx):
            reasons.append("PRE_RUN")
        if reasons:
            return self.skip(*as_reasons(reasons))
        multiplier = 1.0
        if run_3d is not None and rules.neutral_below <= run_3d <= rules.skip_above:
            multiplier = rules.b_multiplier_3_to_6
        elif run_3d is not None and run_3d <= rules.rebound_at_or_below and direction > 0:
            multiplier = rules.b_multiplier_rebound
        day = to_et(ctx.event.as_of).date()
        state = stock_state(
            self._stocks, ctx.event.ticker, day, self._thresholds.modes.A.atr_period
        )
        if state is None:
            return self.skip("DATA_MASSIVE")
        years = years_to(state.day, front_expiration(ctx.event.report_date, ctx.event.report_time))
        collar = self._thresholds.constructions.collar
        iv = options["atm_iv"]
        if direction > 0:
            call_otm = (collar.call_otm_min + collar.call_otm_max) / 2
            cost = collar_cost_fraction(
                self._costs, state.spot, iv, years, self._rate, collar.put_otm, call_otm
            )
            construction = "stock_collar"
        else:
            cost = put_spread_cost_fraction(
                self._costs, state.spot, iv, years, self._rate, collar.put_otm
            )
            construction = "put_spread"
        if cost is None:
            return self.skip("DATA_MASSIVE")
        return Proposal(
            strategy_id=self.id,
            mode=self.mode,
            construction=construction,
            edge=p - (market if direction > 0 else 1 - market),
            confidence=p,
            probability=p,
            cost_fraction=cost,
            size_multiplier=multiplier,
        )

    def _has_reason(self, ctx: DecisionContext) -> bool:
        """Причина роста: раскрытие компании (disclosure ≠ 0) или недавний отчёт информатора."""
        if ctx.features.get("dossier", {}).get("disclosure", 0.0) != 0.0:
            return True
        session = session_of(ctx)
        informants = session.scalars(
            select(orm.PeerEdge.from_ticker).where(orm.PeerEdge.to_ticker == ctx.event.ticker)
        ).all()
        if not informants:
            return False
        day = to_et(ctx.event.as_of).date()
        reported = session.scalars(
            select(orm.EarningsTrack.ticker).where(
                orm.EarningsTrack.ticker.in_(informants),
                orm.EarningsTrack.report_date >= day - timedelta(days=INFORMANT_WINDOW_DAYS),
                orm.EarningsTrack.report_date < day,
            )
        ).first()
        return reported is not None
