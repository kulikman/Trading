"""Состояние плагинов: config/registry.yaml ↔ таблица plugin (решение заказчика 14.10.2026).

registry.yaml задаёт состав плагинов и начальную стадию; текущая стадия живёт в БД и меняется
только командой promote. Повторная синхронизация не трогает стадию уже известного плагина.
"""

from collections.abc import Mapping

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.config.registry import Registry
from core.db import models as orm
from core.domain.plugin import Plugin
from core.domain.types import FeatureStage, PluginStage

STAGES: tuple[PluginStage, ...] = ("shadow", "paper", "live_small", "live")


def influences_decision(stage: PluginStage) -> bool:
    """shadow считает и пишет признаки, но на решение не влияет (SPEC §7)."""
    return stage != "shadow"


def next_stage(stage: PluginStage) -> PluginStage | None:
    """Следующая ступень или None, если плагин уже live."""
    index = STAGES.index(stage)
    return STAGES[index + 1] if index + 1 < len(STAGES) else None


def sync_plugins(session: Session, registry: Registry) -> int:
    """Новые плагины — со стадией из реестра; у известных обновляются только kind и enabled."""
    rows = [
        {"id": p.id, "version": p.version, "kind": p.kind, "stage": p.stage, "enabled": p.enabled}
        for p in registry.plugins
    ]
    if not rows:
        return 0
    statement = insert(orm.Plugin).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["id", "version"],
        set_={
            "kind": statement.excluded.kind,
            "enabled": statement.excluded.enabled,
            "updated_at": func.now(),
        },
    )
    session.execute(statement)
    return len(rows)


def plugin_state(session: Session, plugin_id: str, version: str) -> Plugin | None:
    """Текущее состояние плагина из БД."""
    row = session.get(orm.Plugin, (plugin_id, version))
    return None if row is None else Plugin.model_validate(row, from_attributes=True)


def decision_features(
    session: Session, event_id: int, stage: FeatureStage, registry: Registry
) -> Mapping[str, Mapping[str, float]]:
    """Признаки агентов, влияющих на решение: включённых и не в shadow (версия — из реестра)."""
    versions = {p.id: p.version for p in registry.plugins if p.kind == "agent" and p.enabled}
    states = {
        (row.id, row.version): row.stage
        for row in session.scalars(select(orm.Plugin).where(orm.Plugin.kind == "agent")).all()
    }
    snapshots = session.scalars(
        select(orm.FeatureSnapshot).where(
            orm.FeatureSnapshot.event_id == event_id, orm.FeatureSnapshot.stage == stage
        )
    ).all()
    result: dict[str, Mapping[str, float]] = {}
    for snap in snapshots:
        if versions.get(snap.agent_id) != snap.agent_version:
            continue  # агент выключен или признаки старой версии
        current = states.get((snap.agent_id, snap.agent_version))
        if current is not None and influences_decision(_stage(current)):
            result[snap.agent_id] = snap.features
    return result


def _stage(value: str) -> PluginStage:
    for stage in STAGES:
        if stage == value:
            return stage
    raise ValueError(f"unknown plugin stage {value!r}")
