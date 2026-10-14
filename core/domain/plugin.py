"""Состояние плагина в БД (SPEC §5, §7)."""

from pydantic import AwareDatetime

from core.domain.base import DomainModel, Probability
from core.domain.types import PluginKind, PluginStage, PromotionMetric


class Plugin(DomainModel):
    id: str
    version: str
    kind: PluginKind
    stage: PluginStage
    weight: Probability | None = None
    enabled: bool


class PluginStageChange(DomainModel):
    """Журнал promote: и принятые переходы, и отказы с причиной."""

    id: int | None = None
    plugin_id: str
    version: str
    from_stage: PluginStage
    to_stage: PluginStage | None  # отказ — None
    accepted: bool
    reason: str
    metric: PromotionMetric
    observations: int
    baseline: float | None = None
    candidate: float | None = None
    at: AwareDatetime
