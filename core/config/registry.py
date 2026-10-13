"""Модель config/registry.yaml: включённые агенты и стратегии и их стадии (SPEC §7)."""

from typing import Literal, Self

from pydantic import Field, model_validator

from core.config.base import StrictModel

Stage = Literal["shadow", "paper", "live_small", "live"]
PluginKind = Literal["agent", "strategy"]


class PluginEntry(StrictModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    kind: PluginKind
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    stage: Stage
    enabled: bool


class Registry(StrictModel):
    plugins: list[PluginEntry]

    @model_validator(mode="after")
    def _unique(self) -> Self:
        seen: set[tuple[str, str]] = set()
        for plugin in self.plugins:
            key = (plugin.id, plugin.version)
            if key in seen:
                raise ValueError(f"duplicate plugin {plugin.id} {plugin.version}")
            seen.add(key)
        return self
