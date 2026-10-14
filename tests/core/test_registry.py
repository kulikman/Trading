import dataclasses
import sys
from pathlib import Path

import pytest

from core.config import AppConfig, load_config
from core.config.registry import PluginEntry, Registry
from core.domain.plugin import Plugin
from core.domain.types import PluginKind
from core.registry.loader import RegistryError, load_agents, load_strategies
from core.registry.promote import NoEvidence, PromotionEvidence, decide
from core.registry.state import influences_decision, next_stage

LIFECYCLE = load_config().thresholds.lifecycle  # 30 наблюдений, вес live_small 5%


def plugin(stage: str = "paper", kind: str = "strategy", enabled: bool = True) -> Plugin:
    return Plugin.model_validate(
        {"id": "mode_c", "version": "0.1.0", "kind": kind, "stage": stage, "enabled": enabled}
    )


def test_stage_ladder() -> None:
    assert [next_stage(s) for s in ("shadow", "paper", "live_small", "live")] == [
        "paper",
        "live_small",
        "live",
        None,
    ]
    assert influences_decision("shadow") is False
    assert all(influences_decision(s) for s in ("paper", "live_small", "live"))


@pytest.mark.parametrize(
    ("candidate", "stage", "enabled", "evidence", "reason"),
    [
        ("live", "live", True, PromotionEvidence("sharpe", 50, 1.0, 2.0), "уже live"),
        ("off", "paper", False, PromotionEvidence("sharpe", 50, 1.0, 2.0), "выключен"),
        (
            "few",
            "paper",
            True,
            PromotionEvidence("sharpe", 29, 1.0, 2.0),
            "мало наблюдений: 29 из 30",
        ),
        ("none", "paper", True, PromotionEvidence("sharpe", 30, None, 2.0), "нет метрики sharpe"),
        ("worse", "paper", True, PromotionEvidence("sharpe", 30, 1.2, 1.1), "не лучше базового"),
    ],
)
def test_promote_refuses_with_reason(
    candidate: str, stage: str, enabled: bool, evidence: PromotionEvidence, reason: str
) -> None:
    result = decide(plugin(stage, enabled=enabled), evidence, LIFECYCLE)
    assert (result.accepted, result.to_stage) == (False, None)
    assert reason in result.reason


def test_strategy_needs_higher_sharpe_agent_needs_lower_brier() -> None:
    strategy = decide(plugin("paper"), PromotionEvidence("sharpe", 30, 1.0, 1.3), LIFECYCLE)
    assert (strategy.accepted, strategy.to_stage) == (True, "live_small")
    agent = plugin("shadow", kind="agent")
    better = decide(agent, PromotionEvidence("brier", 40, 0.25, 0.22), LIFECYCLE)
    worse = decide(agent, PromotionEvidence("brier", 40, 0.22, 0.25), LIFECYCLE)
    assert (better.accepted, better.to_stage, worse.accepted) == (True, "paper", False)


def test_no_evidence_until_models_exist() -> None:
    assert NoEvidence().evidence(plugin(kind="agent")) == PromotionEvidence("brier", 0, None, None)
    result = decide(plugin(), NoEvidence().evidence(plugin()), LIFECYCLE)
    assert result.reason == "мало наблюдений: 0 из 30"


AGENT_SOURCE = """
from pydantic import BaseModel


class Out(BaseModel):
    x: float


class Good:
    id = "good"
    version = "{version}"
    triggers = []
    reads = []
    output_schema = Out

    def run(self, ctx):
        return Out(x=1.0)


def create_plugin(config):
    return Good()
"""


@pytest.fixture
def fake_packages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[PluginKind, str]:
    root = tmp_path / "fake_agents"
    for name, body in {
        "good": AGENT_SOURCE.format(version="0.1.0"),
        "wrong_version": AGENT_SOURCE.format(version="9.9.9").replace('"good"', '"wrong_version"'),
        "no_factory": "VALUE = 1\n",
        "not_an_agent": "def create_plugin(config):\n    return object()\n",
    }.items():
        (root / name).mkdir(parents=True)
        (root / name / "__init__.py").write_text("")
        (root / name / "plugin.py").write_text(body)
    (root / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))
    for module in [m for m in sys.modules if m.startswith("fake_agents")]:
        monkeypatch.delitem(sys.modules, module)
    return {"agent": "fake_agents", "strategy": "fake_strategies"}


def config_with(*entries: PluginEntry) -> AppConfig:
    return dataclasses.replace(load_config(), registry=Registry(plugins=list(entries)))


def entry(plugin_id: str, enabled: bool = True, runs: str = "event") -> PluginEntry:
    return PluginEntry.model_validate(
        {
            "id": plugin_id,
            "kind": "agent",
            "version": "0.1.0",
            "stage": "shadow",
            "enabled": enabled,
            "runs": runs,
        }
    )


def test_loader_loads_enabled_event_plugins_only(fake_packages: dict[PluginKind, str]) -> None:
    config = config_with(
        entry("good"), entry("no_factory", enabled=False), entry("calendar", runs="schedule")
    )
    agents = load_agents(config, fake_packages)
    assert list(agents) == ["good"]
    assert load_strategies(config, fake_packages) == {}


@pytest.mark.parametrize(
    ("plugin_id", "message"),
    [
        ("missing", "no module fake_agents.missing.plugin"),
        ("no_factory", "has no create_plugin"),
        ("not_an_agent", "not a agent, missing id"),
        ("wrong_version", "registry says wrong_version 0.1.0, plugin is wrong_version 9.9.9"),
    ],
)
def test_loader_fails_loudly(
    fake_packages: dict[PluginKind, str], plugin_id: str, message: str
) -> None:
    with pytest.raises(RegistryError, match=message):
        load_agents(config_with(entry(plugin_id)), fake_packages)


def test_real_registry_loads_without_errors() -> None:
    config = load_config()
    assert load_agents(config) == {}  # пока включён только календарь (runs: schedule)
    assert load_strategies(config) == {}
