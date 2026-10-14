"""Загрузка плагинов конвейера события по registry.yaml (SPEC §7): ядро не знает их имён.

Соглашение: плагин `<id>` — пакет `agents/<id>/` или `strategies/<id>/` с модулем `plugin.py`
и функцией `create_plugin(config) -> Agent | Strategy`. Загружаются только включённые плагины
с `runs: event`; плагины `runs: schedule` (календарь) запускает своя задача планировщика.
Нет модуля, фабрики или не тот id / версия — RegistryError при старте, а не тихий пропуск.
"""

import importlib
from collections.abc import Mapping
from typing import Any

from core.config import AppConfig
from core.config.registry import PluginEntry
from core.domain.types import PluginKind
from core.registry.protocols import Agent, Strategy

PACKAGES: Mapping[PluginKind, str] = {"agent": "agents", "strategy": "strategies"}
REQUIRED: Mapping[PluginKind, tuple[str, ...]] = {
    "agent": ("id", "version", "triggers", "reads", "output_schema", "run"),
    "strategy": ("id", "version", "mode", "evaluate", "exit_rules"),
}


class RegistryError(Exception):
    """Плагин из реестра не загружается."""


def load_agents(
    config: AppConfig, packages: Mapping[PluginKind, str] = PACKAGES
) -> dict[str, Agent]:
    """Включённые агенты конвейера события."""
    return {e.id: _load(e, config, packages) for e in _entries(config, "agent")}


def load_strategies(
    config: AppConfig, packages: Mapping[PluginKind, str] = PACKAGES
) -> dict[str, Strategy]:
    """Включённые стратегии."""
    return {e.id: _load(e, config, packages) for e in _entries(config, "strategy")}


def _entries(config: AppConfig, kind: PluginKind) -> list[PluginEntry]:
    return [
        p for p in config.registry.plugins if p.kind == kind and p.enabled and p.runs == "event"
    ]


def _load(entry: PluginEntry, config: AppConfig, packages: Mapping[PluginKind, str]) -> Any:
    module_name = f"{packages[entry.kind]}.{entry.id}.plugin"
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise RegistryError(f"{entry.id}: no module {module_name}") from exc
    factory = getattr(module, "create_plugin", None)
    if not callable(factory):
        raise RegistryError(f"{entry.id}: {module_name} has no create_plugin(config)")
    plugin = factory(config)
    missing = [name for name in REQUIRED[entry.kind] if not hasattr(plugin, name)]
    if missing:
        raise RegistryError(f"{entry.id}: not a {entry.kind}, missing {', '.join(missing)}")
    if (plugin.id, plugin.version) != (entry.id, entry.version):
        raise RegistryError(
            f"{entry.id}: registry says {entry.id} {entry.version}, "
            f"plugin is {plugin.id} {plugin.version}"
        )
    return plugin
