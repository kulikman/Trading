import importlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

PACKAGES = [
    "core",
    "core.domain",
    "core.db",
    "core.scheduler",
    "core.registry",
    "core.state_machine",
    "adapters",
    "adapters.massive",
    "adapters.ivolatility",
    "adapters.edgar",
    "adapters.fred",
    "adapters.polymarket",
    "adapters.llm",
    "adapters.broker",
    "agents",
    "strategies",
    "models",
    "decision",
    "execution",
    "notify",
    "notify.telegram",
    "learning",
    "backtest",
    "api",
]


@pytest.mark.parametrize("name", PACKAGES)
def test_package_is_importable_from_repo(name: str) -> None:
    module = importlib.import_module(name)
    assert module.__file__ is not None
    assert Path(module.__file__).resolve().is_relative_to(REPO_ROOT)


def test_env_example_has_no_values() -> None:
    lines = (REPO_ROOT / ".env.example").read_text().splitlines()
    assignments = [line for line in lines if line.strip() and not line.lstrip().startswith("#")]
    assert assignments, ".env.example must list the expected variables"
    filled = [line for line in assignments if line.split("=", 1)[1].strip()]
    assert filled == []
