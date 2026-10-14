"""Команда promote (SPEC §7): подъём плагина на одну ступень по метрикам отложенной выборки.

Условия: наблюдений ≥ lifecycle.promote_min_obs; у агента Brier на отложенной выборке лучше
(меньше) базового, у стратегии Sharpe лучше (больше). Иначе — отказ с причиной.
Каждая попытка (и принятая, и отказ) пишется в журнал plugin_stage_change.
Метрики подаёт EvidenceSource; до моделей (T15) и обучения сезона (T20) их нет — NoEvidence.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from core.config.thresholds import Lifecycle
from core.db import models as orm
from core.domain.plugin import Plugin
from core.domain.types import PluginStage, PromotionMetric
from core.registry.state import next_stage, plugin_state


@dataclass(frozen=True)
class PromotionEvidence:
    metric: PromotionMetric
    observations: int
    baseline: float | None  # метрика текущей версии / базовой модели на отложенной выборке
    candidate: float | None  # метрика плагина


class EvidenceSource(Protocol):
    def evidence(self, plugin: Plugin) -> PromotionEvidence:
        """Метрики плагина на отложенной выборке."""


class NoEvidence:
    """Источник до T15/T20: наблюдений нет — promote честно отказывает."""

    def evidence(self, plugin: Plugin) -> PromotionEvidence:
        return PromotionEvidence(_metric(plugin), 0, None, None)


@dataclass(frozen=True)
class PromotionResult:
    plugin_id: str
    version: str
    from_stage: PluginStage
    to_stage: PluginStage | None
    accepted: bool
    reason: str


def decide(plugin: Plugin, evidence: PromotionEvidence, lifecycle: Lifecycle) -> PromotionResult:
    """Решение без записи в БД."""
    target = next_stage(plugin.stage)

    def refuse(reason: str) -> PromotionResult:
        return PromotionResult(plugin.id, plugin.version, plugin.stage, None, False, reason)

    if target is None:
        return refuse("уже live — выше некуда")
    if not plugin.enabled:
        return refuse("плагин выключен в registry.yaml")
    if evidence.observations < lifecycle.promote_min_obs:
        return refuse(f"мало наблюдений: {evidence.observations} из {lifecycle.promote_min_obs}")
    if evidence.baseline is None or evidence.candidate is None:
        return refuse(f"нет метрики {evidence.metric} на отложенной выборке")
    better = (
        evidence.candidate < evidence.baseline
        if evidence.metric == "brier"
        else evidence.candidate > evidence.baseline
    )
    if not better:
        return refuse(
            f"{evidence.metric} не лучше базового: {evidence.candidate:.4f} против "
            f"{evidence.baseline:.4f}"
        )
    return PromotionResult(
        plugin.id,
        plugin.version,
        plugin.stage,
        target,
        True,
        f"{evidence.metric} {evidence.candidate:.4f} лучше {evidence.baseline:.4f}, "
        f"наблюдений {evidence.observations}",
    )


def promote(
    session: Session,
    plugin_id: str,
    version: str,
    *,
    source: EvidenceSource,
    lifecycle: Lifecycle,
    now: datetime,
) -> PromotionResult:
    """Попытка подъёма: решение, журнал, при согласии — новая стадия и вес в БД."""
    plugin = plugin_state(session, plugin_id, version)
    if plugin is None:
        raise ValueError(
            f"plugin {plugin_id} {version} is not in the database: sync registry first"
        )
    evidence = source.evidence(plugin)
    result = decide(plugin, evidence, lifecycle)
    session.add(
        orm.PluginStageChange(
            plugin_id=plugin.id,
            version=plugin.version,
            from_stage=plugin.stage,
            to_stage=result.to_stage,
            accepted=result.accepted,
            reason=result.reason,
            metric=evidence.metric,
            observations=evidence.observations,
            baseline=evidence.baseline,
            candidate=evidence.candidate,
            at=now,
        )
    )
    if result.accepted and result.to_stage is not None:
        row = session.get(orm.Plugin, (plugin.id, plugin.version))
        if row is None:  # pragma: no cover — состояние только что прочитано
            raise ValueError(f"plugin {plugin.id} disappeared")
        row.stage = result.to_stage
        row.weight = _weight(result.to_stage, lifecycle)
    session.flush()
    return result


def _metric(plugin: Plugin) -> PromotionMetric:
    return "brier" if plugin.kind == "agent" else "sharpe"


def _weight(stage: PluginStage, lifecycle: Lifecycle) -> float | None:
    """live_small — вес 5% (SPEC §7), live — полный; ниже — вес не задаётся."""
    if stage == "live_small":
        return lifecycle.live_small_weight
    return 1.0 if stage == "live" else None
