"""Состояние плагина в БД (SPEC §5, §7)."""

from core.domain.base import DomainModel, Probability
from core.domain.types import PluginKind, PluginStage


class Plugin(DomainModel):
    id: str
    version: str
    kind: PluginKind
    stage: PluginStage
    weight: Probability | None = None
    enabled: bool
