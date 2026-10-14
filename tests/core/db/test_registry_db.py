from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import load_config
from core.config.registry import PluginEntry, Registry
from core.db import models as orm
from core.db.store import sync_universe
from core.domain.plugin import Plugin
from core.registry.promote import NoEvidence, PromotionEvidence, promote
from core.registry.state import decision_features, plugin_state, sync_plugins

CONFIG = load_config()
NOW = datetime(2026, 10, 14, 15, tzinfo=UTC)


def entry(plugin_id: str, stage: str, enabled: bool = True, kind: str = "agent") -> PluginEntry:
    return PluginEntry.model_validate(
        {
            "id": plugin_id,
            "kind": kind,
            "version": "0.1.0",
            "stage": stage,
            "enabled": enabled,
            "runs": "event",
        }
    )


REGISTRY = Registry(
    plugins=[
        entry("options", "paper"),
        entry("polymarket", "shadow"),
        entry("macro", "paper", enabled=False),
        entry("mode_c", "paper", kind="strategy"),
    ]
)


class Evidence:
    def __init__(self, evidence: PromotionEvidence) -> None:
        self.value = evidence

    def evidence(self, plugin: Plugin) -> PromotionEvidence:
        return self.value


def stage_of(session: Session, plugin_id: str) -> str | None:
    state = plugin_state(session, plugin_id, "0.1.0")
    return None if state is None else state.stage


def test_sync_keeps_stage_from_db_and_updates_enabled(session: Session) -> None:
    assert sync_plugins(session, REGISTRY) == 4
    row = session.get(orm.Plugin, ("options", "0.1.0"))
    assert row is not None
    row.stage = "live_small"  # как после promote
    changed = Registry(plugins=[entry("options", "shadow", enabled=False), *REGISTRY.plugins[1:]])
    sync_plugins(session, changed)
    session.expire_all()
    options = plugin_state(session, "options", "0.1.0")
    assert options is not None
    assert (options.stage, options.enabled) == ("live_small", False)  # стадия — из БД


def test_promote_refusal_and_success_are_journaled(session: Session) -> None:
    sync_plugins(session, REGISTRY)
    refused = promote(
        session,
        "mode_c",
        "0.1.0",
        source=NoEvidence(),
        lifecycle=CONFIG.thresholds.lifecycle,
        now=NOW,
    )
    assert (refused.accepted, refused.reason) == (False, "мало наблюдений: 0 из 30")
    assert stage_of(session, "mode_c") == "paper"
    accepted = promote(
        session,
        "mode_c",
        "0.1.0",
        source=Evidence(PromotionEvidence("sharpe", 42, 0.8, 1.1)),
        lifecycle=CONFIG.thresholds.lifecycle,
        now=NOW,
    )
    assert (accepted.accepted, accepted.to_stage) == (True, "live_small")
    row = session.get(orm.Plugin, ("mode_c", "0.1.0"))
    assert row is not None
    assert (row.stage, row.weight) == ("live_small", 0.05)  # вес 5% — SPEC §7
    journal = session.scalars(
        select(orm.PluginStageChange).order_by(orm.PluginStageChange.id)
    ).all()
    assert [(j.accepted, j.from_stage, j.to_stage, j.observations) for j in journal] == [
        (False, "paper", None, 0),
        (True, "paper", "live_small", 42),
    ]


def test_promote_unknown_plugin_needs_sync(session: Session) -> None:
    with pytest.raises(ValueError, match="sync registry first"):
        promote(
            session,
            "ghost",
            "0.1.0",
            source=NoEvidence(),
            lifecycle=CONFIG.thresholds.lifecycle,
            now=NOW,
        )


def test_shadow_agent_writes_features_but_does_not_reach_decision(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    sync_plugins(session, REGISTRY)
    event = orm.Event(ticker="NFLX", report_date=date(2026, 10, 20), date_status="projected")
    session.add(event)
    session.flush()
    for agent_id, version in [
        ("options", "0.1.0"),  # paper — влияет
        ("polymarket", "0.1.0"),  # shadow — пишет, но не влияет
        ("macro", "0.1.0"),  # выключен
        ("options", "0.0.9"),  # старая версия
    ]:
        session.add(
            orm.FeatureSnapshot(
                event_id=event.id,
                stage="T-1",
                agent_id=agent_id,
                agent_version=version,
                features={"x": 1.0},
            )
        )
    session.flush()
    stored = session.scalars(select(orm.FeatureSnapshot.agent_id)).all()
    assert "polymarket" in stored  # признаки shadow сохранены
    assert dict(decision_features(session, event.id, "T-1", REGISTRY)) == {"options": {"x": 1.0}}
