"""Событие отчёта, история отчётов, признаки и прогнозы (SPEC §5)."""

from datetime import date
from decimal import Decimal
from typing import Any, Self

from pydantic import Field, model_validator

from core.domain.base import DomainModel, Probability
from core.domain.types import (
    DateCheckStatus,
    DateStatus,
    DecisionStatus,
    Direction,
    FeatureStage,
    QueueStatus,
    ReportTime,
    SkipReason,
)

MIN_DATE_SOURCES_FOR_CONFIRMED = 2  # SPEC §6: дата подтверждена только двумя источниками


class Event(DomainModel):
    id: int | None = None
    ticker: str
    report_date: date
    report_time: ReportTime | None = None
    fiscal_period: str | None = None
    date_status: DateStatus
    date_sources: list[dict[str, Any]] = Field(default_factory=list)
    queue_status: QueueStatus = "planned"

    @model_validator(mode="after")
    def _confirmed_needs_two_sources(self) -> Self:
        is_confirmed = self.date_status == "confirmed"
        if is_confirmed and len(self.date_sources) < MIN_DATE_SOURCES_FOR_CONFIRMED:
            raise ValueError("confirmed report date needs at least 2 date_sources")
        return self


class EarningsTrack(DomainModel):
    id: int | None = None
    ticker: str
    report_date: date
    report_time: ReportTime | None = None
    fiscal_period_end: date | None = None  # конец фискального квартала — ключ к выручке SEC
    sec_filing_date: date | None = None  # подача 8-K о результатах, ближайшая к дате отчёта
    date_check: DateCheckStatus | None = (
        None  # mismatch — дата источника под сомнением (T12 исключает)
    )
    eps_consensus: float | None = None
    eps_actual: float | None = None
    eps_surprise_pct: float | None = None
    rev_consensus: float | None = None
    rev_actual: float | None = None
    rev_surprise_pct: float | None = None
    guidance_change: Direction | None = None
    implied_move: float | None = None
    actual_move: float | None = None
    move_ratio: float | None = None
    reaction_cause: str | None = None
    model_p_beat: Probability | None = None
    model_p_up: Probability | None = None
    model_move_ratio: Probability | None = None
    decision: DecisionStatus | None = None
    skip_reasons: list[SkipReason] | None = None
    shadow_pnl: Decimal | None = None


class ReportedEarnings(DomainModel):
    """Прошлый отчёт из истории EPS (Alpha Vantage EARNINGS): дата, время, консенсус и факт.

    EPS — скорректированный (non-GAAP, как у источника); сюрприз — в процентах: 12.5 = +12,5%.
    """

    ticker: str
    report_date: date
    report_time: ReportTime | None = None
    fiscal_period_end: date
    eps_consensus: float | None = None
    eps_actual: float | None = None
    eps_surprise_pct: float | None = None


class ReportAudit(DomainModel):
    id: int | None = None
    ticker: str
    fiscal_period: str
    report_date: date
    segments_expected: Any | None = None
    segments_actual: Any | None = None
    guidance: Any | None = None
    management_tone: float | None = None
    named_risks: Any | None = None
    summary: str | None = None
    source_urls: list[str] | None = None


class ConsensusSnapshot(DomainModel):
    ticker: str
    fiscal_period: str
    as_of: date
    eps_estimate: float | None = None
    rev_estimate: float | None = None


class FeatureSnapshot(DomainModel):
    """Только числа (SPEC §5): текст для человека хранится отдельно."""

    event_id: int
    stage: FeatureStage
    agent_id: str
    agent_version: str
    features: dict[str, float]


class Forecast(DomainModel):
    event_id: int
    stage: FeatureStage
    model_version: str
    p_beat: Probability | None = None
    p_up: Probability | None = None
    move_ratio: Probability | None = None
    market_p_beat: Probability | None = None
    market_p_up: Probability | None = None
    implied_move: float | None = None
    edge_beat: float | None = None
    edge_up: float | None = None
    edge_move: float | None = None
    exploration: bool = False
