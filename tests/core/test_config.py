import shutil
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel

from core.config import (
    DEFAULT_CONFIG_DIR,
    ConfigError,
    Thresholds,
    load_config,
    load_registry,
    load_thresholds,
    load_universe,
)

Mutation = Callable[[dict[str, Any]], None]


@pytest.fixture
def config_dir(tmp_path: Path) -> Path:
    target = tmp_path / "config"
    shutil.copytree(DEFAULT_CONFIG_DIR, target)
    return target


def _mutate(path: Path, mutation: Mutation) -> None:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    mutation(data)
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


# --- реальные конфиги ---


def test_repository_config_loads() -> None:
    config = load_config()
    assert len(config.universe.tickers()) == 50
    assert config.thresholds.capital.module_usd == 100_000
    assert config.thresholds.risk_limits.cluster_max_positions is None
    assert config.thresholds.risk_limits.season_max_open_risk is None


def test_every_sector_has_at_least_three_companies() -> None:
    universe = load_config().universe
    assert all(len(sector.companies) >= 3 for sector in universe.sectors)


def test_registry_starting_stages_match_spec_17_4() -> None:
    stages = {p.id: p.stage for p in load_config().registry.plugins if p.kind == "strategy"}
    assert stages["mode_a"] == "shadow"
    assert stages["mode_b"] == "shadow"
    assert stages["mode_c"] == "paper"
    assert stages["straddle"] == "paper"
    assert stages["iron_condor"] == "paper"


def test_sector_of_returns_sector_and_rejects_unknown_ticker() -> None:
    universe = load_config().universe
    assert universe.sector_of("GS").id == "banks"
    with pytest.raises(KeyError):
        universe.sector_of("ZZZZ")


# --- пороги только в config/ ---


def _fields_with_defaults(model: type[BaseModel], prefix: str = "") -> list[str]:
    found: list[str] = []
    for name, field in model.model_fields.items():
        if not field.is_required():
            found.append(prefix + name)
        annotation = field.annotation
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            found += _fields_with_defaults(annotation, f"{prefix}{name}.")
    return found


def test_thresholds_have_no_defaults_in_code() -> None:
    assert _fields_with_defaults(Thresholds) == []


# --- невалидные конфиги дают понятную ошибку ---


def _walk(data: dict[str, Any], keys: str) -> tuple[Any, str | int]:
    """Путь вида `plugins.0.stage`: числа — индексы списков."""
    parts: list[str | int] = [int(k) if k.isdigit() else k for k in keys.split(".")]
    node: Any = data
    for key in parts[:-1]:
        node = node[key]
    return node, parts[-1]


def _set(keys: str, value: object) -> Mutation:
    def mutation(data: dict[str, Any]) -> None:
        node, last = _walk(data, keys)
        node[last] = value

    return mutation


def _delete(keys: str) -> Mutation:
    def mutation(data: dict[str, Any]) -> None:
        node, last = _walk(data, keys)
        del node[last]

    return mutation


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (_set("sizing.kelly_multiplier", 1.5), "sizing.kelly_multiplier"),
        (_set("sizing.kelly_multiplier", "0.25"), "sizing.kelly_multiplier"),
        (_delete("capital.module_usd"), "capital.module_usd: Field required"),
        (_set("capital.typo_key", 1), "capital.typo_key: Extra inputs are not permitted"),
        (_set("risk_limits.drawdown.manual_review", 0.2), "manual_review must be below"),
        (_set("constructions.iron_condor.max_move_ratio", 1.5), "iron_condor.max_move_ratio"),
        (_set("pre_run_3d.rebound_at_or_below", 0.04), "pre_run_3d.rebound_at_or_below"),
    ],
)
def test_invalid_thresholds_fail_with_field_path(
    config_dir: Path, mutation: Mutation, expected: str
) -> None:
    path = config_dir / "thresholds.yaml"
    _mutate(path, mutation)
    with pytest.raises(ConfigError, match=r"thresholds\.yaml") as exc_info:
        load_thresholds(path)
    assert expected in str(exc_info.value)


def _add_company(sector_index: int, ticker: object) -> Mutation:
    def mutation(data: dict[str, Any]) -> None:
        data["sectors"][sector_index]["companies"].append({"ticker": ticker, "name": "X"})

    return mutation


def _add_edge(from_ticker: str, to_ticker: str) -> Mutation:
    def mutation(data: dict[str, Any]) -> None:
        data["peer_edges"].append({"from_ticker": from_ticker, "to_ticker": to_ticker})

    return mutation


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (_add_company(1, "JPM"), "duplicate ticker: JPM"),
        (_add_company(0, "jpmx"), "ticker"),
        (_add_company(0, True), "ticker"),  # YAML превращает тикер ON/NO/YES в bool
        (_add_edge("JPM", "ZZZZ"), "ZZZZ, which is not in any sector"),
        (_add_edge("JPM", "JPM"), "JPM → itself"),
        (_add_edge("JPM", "BAC"), "duplicate peer edge"),
        (_set("sectors.0.macro_sensitivity", ["oil"]), "macro_sensitivity"),
    ],
)
def test_invalid_universe_fails_with_reason(
    config_dir: Path, mutation: Mutation, expected: str
) -> None:
    path = config_dir / "universe.yaml"
    _mutate(path, mutation)
    with pytest.raises(ConfigError, match=r"universe\.yaml") as exc_info:
        load_universe(path)
    assert expected in str(exc_info.value)


def _registry_append(entry: dict[str, object]) -> Mutation:
    def mutation(data: dict[str, Any]) -> None:
        data["plugins"].append(entry)

    return mutation


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (_set("plugins.0.stage", "production"), "plugins.0.stage"),
        (_set("plugins.0.version", "1"), "plugins.0.version"),
        (_set("plugins.0.kind", "model"), "plugins.0.kind"),
        (
            _registry_append(
                {
                    "id": "calendar",
                    "kind": "agent",
                    "version": "0.1.0",
                    "stage": "shadow",
                    "enabled": False,
                }
            ),
            "duplicate plugin calendar 0.1.0",
        ),
    ],
)
def test_invalid_registry_fails_with_reason(
    config_dir: Path, mutation: Mutation, expected: str
) -> None:
    path = config_dir / "registry.yaml"
    _mutate(path, mutation)
    with pytest.raises(ConfigError, match=r"registry\.yaml") as exc_info:
        load_registry(path)
    assert expected in str(exc_info.value)


# --- файл отсутствует или не парсится ---


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="file not found"):
        load_thresholds(tmp_path / "thresholds.yaml")


def test_malformed_yaml(tmp_path: Path) -> None:
    path = tmp_path / "registry.yaml"
    path.write_text("plugins: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid YAML"):
        load_registry(path)


def test_top_level_must_be_mapping(tmp_path: Path) -> None:
    path = tmp_path / "universe.yaml"
    path.write_text("- just\n- a list\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="top level must be a mapping"):
        load_universe(path)
