"""Загрузка и валидация config/*.yaml. Любая ошибка — ConfigError с файлом и путём до поля."""

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from core.config.registry import Registry
from core.config.sources import Sources
from core.config.thresholds import Thresholds
from core.config.universe import Universe

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


class ConfigError(Exception):
    """Конфиг отсутствует, не парсится или не проходит валидацию."""


@dataclass(frozen=True)
class AppConfig:
    universe: Universe
    thresholds: Thresholds
    registry: Registry
    sources: Sources


def load_universe(path: Path) -> Universe:
    """Читает и валидирует universe.yaml."""
    return _load(path, Universe)


def load_thresholds(path: Path) -> Thresholds:
    """Читает и валидирует thresholds.yaml."""
    return _load(path, Thresholds)


def load_registry(path: Path) -> Registry:
    """Читает и валидирует registry.yaml."""
    return _load(path, Registry)


def load_sources(path: Path) -> Sources:
    """Читает и валидирует sources.yaml."""
    return _load(path, Sources)


def load_config(config_dir: Path = DEFAULT_CONFIG_DIR) -> AppConfig:
    """Читает все файлы из каталога config/."""
    return AppConfig(
        universe=load_universe(config_dir / "universe.yaml"),
        thresholds=load_thresholds(config_dir / "thresholds.yaml"),
        registry=load_registry(config_dir / "registry.yaml"),
        sources=load_sources(config_dir / "sources.yaml"),
    )


def _load[M: BaseModel](path: Path, model: type[M]) -> M:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"{path}: file not found") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"{path}: invalid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level must be a mapping")
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        raise ConfigError(_describe(path, exc)) from exc


def _describe(path: Path, exc: ValidationError) -> str:
    lines = [f"{path}: {exc.error_count()} error(s)"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"]) or "<root>"
        lines.append(f"  {location}: {error['msg']}")
    return "\n".join(lines)


__all__ = [
    "AppConfig",
    "ConfigError",
    "Registry",
    "Sources",
    "Thresholds",
    "Universe",
    "load_config",
    "load_registry",
    "load_sources",
    "load_thresholds",
    "load_universe",
]
