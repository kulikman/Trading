"""Загрузка и валидация config/*.yaml. Любая ошибка — ConfigError с файлом и путём до поля."""

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from core.config.broker import BrokerConfig
from core.config.registry import Registry
from core.config.schedule import ScheduleConfig
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
    broker: BrokerConfig
    schedule: ScheduleConfig


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


def load_broker(path: Path) -> BrokerConfig:
    """Читает и валидирует broker.yaml."""
    return _load(path, BrokerConfig)


def load_schedule(path: Path) -> ScheduleConfig:
    """Читает и валидирует schedule.yaml."""
    return _load(path, ScheduleConfig)


def load_config(config_dir: Path = DEFAULT_CONFIG_DIR) -> AppConfig:
    """Читает все файлы из каталога config/.

    Если в Redis есть ключ `universe:watchlist_active` (список тикеров JSON),
    и watchlist.yaml существует — активные тикеры временно добавляются в Universe.
    """
    universe = load_universe(config_dir / "universe.yaml")
    watchlist_path = config_dir / "watchlist.yaml"
    if watchlist_path.exists():
        universe = _apply_watchlist_additions(universe, watchlist_path)
    return AppConfig(
        universe=universe,
        thresholds=load_thresholds(config_dir / "thresholds.yaml"),
        registry=load_registry(config_dir / "registry.yaml"),
        sources=load_sources(config_dir / "sources.yaml"),
        broker=load_broker(config_dir / "broker.yaml"),
        schedule=load_schedule(config_dir / "schedule.yaml"),
    )


def _apply_watchlist_additions(universe: Universe, watchlist_path: Path) -> Universe:
    """Читает активные тикеры из Redis и мержит их из watchlist в Universe."""
    import json
    import logging
    import os

    import redis as _redis
    from redis.backoff import NoBackoff
    from redis.retry import Retry

    logger = logging.getLogger(__name__)
    REDIS_KEY = "universe:watchlist_active"

    url = os.environ.get("REDIS_URL", "").strip()
    if not url:
        return universe
    try:
        client = _redis.Redis.from_url(
            url,
            socket_connect_timeout=2.0,
            socket_timeout=2.0,
            retry=Retry(NoBackoff(), 0),
        )
        raw = client.get(REDIS_KEY)
    except Exception:
        logger.warning("watchlist: Redis unavailable, skipping dynamic additions")
        return universe
    if not raw:
        return universe
    try:
        active_tickers: list[str] = json.loads(raw)
    except Exception:
        logger.warning("watchlist: invalid JSON in Redis key %s", REDIS_KEY)
        return universe
    if not active_tickers:
        return universe
    watchlist = load_universe(watchlist_path)
    added = [t for t in active_tickers if t not in set(universe.tickers())]
    if added:
        logger.info("watchlist: activating %d tickers for this week: %s", len(added), added)
    return universe.with_watchlist_additions(active_tickers, watchlist)


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
    "BrokerConfig",
    "ConfigError",
    "Registry",
    "Sources",
    "Thresholds",
    "Universe",
    "load_broker",
    "load_config",
    "load_registry",
    "load_schedule",
    "load_sources",
    "load_thresholds",
    "load_universe",
]
