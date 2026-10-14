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


class LevelThresholds(StrictModel):
    yellow: PositiveFloat | None  # null — у сигнала нет жёлтого порога
    orange: PositiveFloat
    red: PositiveFloat

    @model_validator(mode="after")
    def _increasing(self) -> Self:
        steps = [v for v in (self.yellow, self.orange, self.red) if v is not None]
        if steps != sorted(steps) or len(set(steps)) != len(steps):
            raise ValueError("black swan thresholds must increase from yellow to red")
        return self


class BlackSwanRule(StrictModel):
    """Правило уровня (решение заказчика 13.10.2026): худший из сигналов VIX и SPY."""

    vix_levels: LevelThresholds
    vix_jump: LevelThresholds
    spy_drop: LevelThresholds
    spy_drop_window_days: PositiveInt
    calm_days_to_downgrade: PositiveInt


class BlackSwan(StrictModel):
    yellow: BlackSwanLevel
    orange: BlackSwanLevel
    red: BlackSwanLevel
    rule: BlackSwanRule


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
    # Признаки, которые идут в модели: «агент.признак». Остальные агенты пишут, но модели не видят.
    active_features: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def _within_budget(self) -> Self:
        if len(self.active_features) > self.feature_budget:
            raise ValueError(
                f"{len(self.active_features)} active features exceed feature_budget "
                f"{self.feature_budget}"
            )
        if len(set(self.active_features)) != len(self.active_features):
            raise ValueError("duplicate active features")
        bad = [f for f in self.active_features if f.count(".") != 1]
        if bad:
            raise ValueError(f"active features must be agent.feature: {bad}")
        return self


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


class BacktestModeC(StrictModel):
    """Упрощённый режим C в бэктесте (T12b): без выручки и guidance — их истории нет."""

    decision_time_et: time
    fill_deadline_et: time
    volume_lookback_days: PositiveInt
    min_volume_history_days: PositiveInt
    assumed_spread_stock: Fraction

    @field_validator("decision_time_et", "fill_deadline_et", mode="before")
    @classmethod
    def _time(cls, value: object) -> object:
        return time.fromisoformat(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def _deadline_after_decision(self) -> Self:
        if self.fill_deadline_et <= self.decision_time_et:
            raise ValueError("backtest.mode_c.fill_deadline_et must be after decision_time_et")
        return self


class Backtest(StrictModel):
    """Бэктест T12: сигнал по истории движений, выход, риск для кривой капитала."""

    signal_lookback_reports: PositiveInt
    signal_min_reports: PositiveInt
    exit_time_et: time
    open_slippage_minutes: PositiveInt
    risk_per_trade: Fraction
    compare_condor_stops: list[CondorStopBasis] = Field(min_length=1)
    mode_c: BacktestModeC

    @field_validator("exit_time_et", mode="before")
    @classmethod
    def _time(cls, value: object) -> object:
        return time.fromisoformat(value) if isinstance(value, str) else value

    @model_validator(mode="after")
    def _min_within_lookback(self) -> Self:
        if self.signal_min_reports > self.signal_lookback_reports:
            raise ValueError("backtest.signal_min_reports must not exceed signal_lookback_reports")
        return self


class SectorAgent(StrictModel):
    """«Тренд сектора» (решение заказчика 14.10.2026): знак среднего сюрприза отчитавшихся."""

    season_window_days: PositiveInt
    min_peers: PositiveInt
    min_abs_surprise: Fraction
    momentum_days: PositiveInt


class PositioningAgent(StrictModel):
    long_run_days: PositiveInt  # pre_run_30d — календарные дни
    short_run_trading_days: PositiveInt  # pre_run_3d — торговые дни
    volume_lookback_days: PositiveInt
    short_interest_lag_days: PositiveInt  # публикация FINRA — через ~8 рабочих дней после расчёта


class MacroAgent(StrictModel):
    lookback_days: PositiveInt  # история VIX и SPY для уровня Black Swan


class OptionsAgent(StrictModel):
    """«Опционы» по дневным ценам контрактов (снимка цепочки нет на тарифе — 403, 14.10.2026)."""

    skew_delta: Fraction  # skew_25d — путы и коллы с |Δ| = 0.25
    term_back_min_days: PositiveInt  # дальняя экспирация term_slope — не раньше ближней + N дней
    term_back_window_days: PositiveInt  # и не позже ближней + min + window
    iv_rank_reports: PositiveInt  # прошлых отчётов для iv_rank
    iv_rank_min_reports: PositiveInt  # меньше — iv_rank не считается
    history_days: PositiveInt  # цены акции и ставка — на глубину архива опционов
    rate_max_age_days: PositiveInt  # DGS3MO старше — DataError, ставку не угадываем

    @model_validator(mode="after")
    def _min_not_above_reports(self) -> Self:
        if self.iv_rank_min_reports > self.iv_rank_reports:
            raise ValueError("iv_rank_min_reports must not exceed iv_rank_reports")
        return self


class ConsensusAgent(StrictModel):
    """«Консенсус» по EARNINGS_ESTIMATES Alpha Vantage (25 запросов в день)."""

    min_abs_eps: PositiveFloat  # знаменатель пересмотра и разброса не меньше — EPS около нуля
    max_quarter_lag_days: (
        PositiveInt  # конец фискального квартала не раньше чем за N дней до отчёта
    )


class DossierAgent(StrictModel):
    """«Досье» (решения заказчика 14.10.2026): disclosure, guidance_risk на T−10, итог на T+1."""

    release_lookback_days: PositiveInt  # прошлый пресс-релиз (8-K п. 2.02) — не старше N дней
    disclosure_items: list[str] = Field(min_length=1)  # пункты 8-K, которые читаются как раскрытия
    max_filings: PositiveInt  # последних подач 8-K в запросе
    max_news: PositiveInt  # последних новостей Massive в запросе
    max_chars_per_document: PositiveInt  # документ длиннее обрезается
    max_chars_per_request: PositiveInt  # потолок текста одного запроса к LLM (стоимость)
    release_window_days: int = Field(ge=0)  # T+1: пресс-релиз подан не позже даты отчёта + N дней
    revenue_sanity_ratio: float = Field(
        gt=1
    )  # середина прогноза выручки дальше от консенсуса — ошибка единиц


class Agents(StrictModel):
    sector: SectorAgent
    positioning: PositioningAgent
    macro: MacroAgent
    options: OptionsAgent
    consensus: ConsensusAgent
    dossier: DossierAgent


class PathToReal(StrictModel):
    """Критерии перехода Paper → Real (решение заказчика 2026-10-13, DASHBOARD.md §4.6)."""

    min_trades: PositiveInt
    min_sharpe: float
    max_drawdown: Fraction
    min_paper_days: PositiveInt


class Dashboard(StrictModel):
    """Пороги и интервалы дашборда (T19a, DASHBOARD.md §4.3, §5)."""

    path_to_real: PathToReal
    balance_divergence: Fraction  # расхождение баланса брокера с расчётом → «СИСТЕМА»
    cost_divergence: Fraction  # строка доверия: издержки Paper против реальности
    sharpe_min_days: PositiveInt  # Sharpe по дням — не меньше N дней с P&L
    refresh_session_seconds: PositiveInt
    refresh_off_session_seconds: PositiveInt
    system_failure_window_hours: PositiveInt  # сбой задачи за это окно → «СИСТЕМА: СБОЙ»


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
    agents: Agents
    dashboard: Dashboard
