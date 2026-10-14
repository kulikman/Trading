"""Модель config/thresholds.yaml. У полей нет значений по умолчанию: числа живут только в YAML."""

from datetime import time
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from core.config.base import Fraction, PositiveFloat, PositiveInt, StrictModel


class Capital(StrictModel):
    module_usd: PositiveFloat


class Sizing(StrictModel):
    kelly_multiplier: Fraction
    kelly_multiplier_seasons_1_2: Fraction
    kelly_initial_b: PositiveFloat
    stop_implied_moves: PositiveFloat
    max_risk_per_trade: Fraction | None


class LosingStreak(StrictModel):
    losses: PositiveInt
    pause_hours: PositiveInt


class Drawdown(StrictModel):
    manual_review: Fraction
    paper_only: Fraction

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.manual_review >= self.paper_only:
            raise ValueError("manual_review must be below paper_only")
        return self


class BlackSwanLevel(StrictModel):
    size_multiplier: Fraction
    min_confidence: Fraction | None


class BlackSwan(StrictModel):
    yellow: BlackSwanLevel
    orange: BlackSwanLevel
    red: BlackSwanLevel


class RiskLimits(StrictModel):
    cluster_max_positions: PositiveInt | None
    season_max_open_risk: Fraction | None
    losing_streak: LosingStreak
    drawdown: Drawdown
    black_swan: BlackSwan


class Liquidity(StrictModel):
    max_option_spread: Fraction
    max_stock_spread: Fraction


class Edge(StrictModel):
    margin_over_costs: Fraction
    paper_theta_seasons_1_2: Fraction
    exploration_share_seasons_1_2: Fraction


class Quarantine(StrictModel):
    max_brier: Fraction
    min_reports: PositiveInt


class Models(StrictModel):
    holdout_fraction: Fraction
    isotonic_min_obs: PositiveInt
    min_segment_obs: PositiveInt
    feature_budget: PositiveInt
    feature_merge_correlation: Fraction
    quarantine: Quarantine
    p_up_initial_betas: dict[str, float] = Field(min_length=1)


class Lifecycle(StrictModel):
    promote_min_obs: PositiveInt
    live_small_weight: Fraction


class ModeA(StrictModel):
    max_pre_run_30d: float
    max_vix: PositiveFloat
    min_sector_trend: float
    stop_atr_multiple: PositiveFloat
    atr_period: PositiveInt


class ModeB(StrictModel):
    theta: Fraction


class ModeC(StrictModel):
    min_eps_surprise: Fraction
    min_revenue_surprise: Fraction
    min_volume_ratio: PositiveFloat
    max_entry_over_vwap: Fraction
    trailing_atr_multiple: PositiveFloat
    atr_period: PositiveInt
    exit_sma_period: PositiveInt
    max_hold_days: PositiveInt


class Modes(StrictModel):
    A: ModeA
    B: ModeB
    C: ModeC


class PreRun3d(StrictModel):
    neutral_below: Fraction
    skip_above: Fraction
    b_multiplier_3_to_6: PositiveFloat
    rebound_at_or_below: float = Field(lt=0)
    b_multiplier_rebound: PositiveFloat

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.neutral_below >= self.skip_above:
            raise ValueError("neutral_below must be below skip_above")
        return self


class Collar(StrictModel):
    put_otm: Fraction
    call_otm_min: Fraction
    call_otm_max: Fraction

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.call_otm_min > self.call_otm_max:
            raise ValueError("call_otm_min must not exceed call_otm_max")
        return self


class Straddle(StrictModel):
    min_move_ratio: PositiveFloat
    stop_premium_loss: Fraction
    target_premium_gain: PositiveFloat


# Стоп кондора: cost — выкуп стоит N× премии (убыток = (N − 1)× премии), loss — убыток N× премии.
CondorStopBasis = Literal["cost", "loss"]


class IronCondor(StrictModel):
    max_move_ratio: PositiveFloat
    stop_premium_multiple: PositiveFloat
    stop_basis: CondorStopBasis
    target_premium_share: Fraction
    short_implied_moves: PositiveFloat
    wing_implied_moves: PositiveFloat

    @model_validator(mode="after")
    def _wings_outside(self) -> Self:
        if self.wing_implied_moves <= self.short_implied_moves:
            raise ValueError("iron_condor.wing_implied_moves must exceed short_implied_moves")
        return self


class PolymarketConstruction(StrictModel):
    min_edge: Fraction


class Constructions(StrictModel):
    collar: Collar
    straddle: Straddle
    iron_condor: IronCondor
    polymarket: PolymarketConstruction

    @model_validator(mode="after")
    def _no_overlap(self) -> Self:
        if self.iron_condor.max_move_ratio >= self.straddle.min_move_ratio:
            raise ValueError("iron_condor.max_move_ratio must be below straddle.min_move_ratio")
        return self


class Data(StrictModel):
    max_price_mismatch: Fraction


class Execution(StrictModel):
    no_market_orders_first_minutes: PositiveInt
    fill_reminder_minutes: PositiveInt


class Costs(StrictModel):
    paper_vs_real_alert: Fraction


class Notify(StrictModel):
    watchdog_grace_minutes: PositiveInt


class Backtest(StrictModel):
    """Бэктест T12: сигнал по истории движений, выход, риск для кривой капитала."""

    signal_lookback_reports: PositiveInt
    signal_min_reports: PositiveInt
    exit_time_et: time
    open_slippage_minutes: PositiveInt
    risk_per_trade: Fraction
    compare_condor_stops: list[CondorStopBasis] = Field(min_length=1)

    @field_validator("exit_time_et", mode="before")
    @classmethod
    def _time(cls, value: object) -> object:
        return time.fromisoformat(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def _min_within_lookback(self) -> Self:
        if self.signal_min_reports > self.signal_lookback_reports:
            raise ValueError("backtest.signal_min_reports must not exceed signal_lookback_reports")
        return self


class Thresholds(StrictModel):
    capital: Capital
    sizing: Sizing
    risk_limits: RiskLimits
    liquidity: Liquidity
    edge: Edge
    models: Models
    lifecycle: Lifecycle
    modes: Modes
    pre_run_3d: PreRun3d
    constructions: Constructions
    data: Data
    execution: Execution
    costs: Costs
    notify: Notify
    backtest: Backtest
