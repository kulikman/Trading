"""Сектора, компании и граф информаторов (SPEC §5)."""

from datetime import date
from typing import Any, Self

from pydantic import Field, model_validator

from core.domain.base import DomainModel, Probability
from core.domain.types import CalibrationStatus, Direction


class Sector(DomainModel):
    id: str
    name: str
    key_metrics: list[str] = Field(min_length=1)
    macro_sensitivity: list[str] | None = None
    data_sources: Any | None = None


class SectorSummary(DomainModel):
    id: int | None = None
    sector_id: str
    as_of: date
    trend: Direction | None = None
    confidence: Probability | None = None
    peer_surprise_mean: float | None = None
    sector_momentum_30d: float | None = None
    facts: Any | None = None
    risks: Any | None = None
    text_summary: str | None = None


class Company(DomainModel):
    ticker: str
    sector_id: str
    name: str
    overview: str | None = None
    segments: Any | None = None
    risks: Any | None = None
    options_liquid: bool | None = None
    calibration_status: CalibrationStatus = "active"


class PeerEdge(DomainModel):
    from_ticker: str
    to_ticker: str
    strength: float | None = Field(default=None, ge=-1, le=1)
    lag_days: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _not_self(self) -> Self:
        if self.from_ticker == self.to_ticker:
            raise ValueError("peer edge cannot point to itself")
        return self
