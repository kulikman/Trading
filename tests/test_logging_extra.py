"""Ключи `extra=` в логах не должны совпадать с полями LogRecord.

Иначе `logging` бросает KeyError в момент записи — и только на том уровне, который включён
в работе (в тестах INFO обычно выключен). Так упал первый живой прогон «Календаря» 14.10.2026.
"""

import ast
import logging
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("adapters", "agents", "core", "execution", "notify", "backtest")
RESERVED = set(logging.LogRecord("n", 0, "p", 0, "m", None, None).__dict__) | {
    "message",
    "asctime",
}


def collisions() -> list[str]:
    found = []
    for folder in SOURCE_DIRS:
        for path in sorted((ROOT / folder).rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not (isinstance(node, ast.keyword) and node.arg == "extra"):
                    continue
                if not isinstance(node.value, ast.Dict):
                    continue
                keys = {
                    k.value
                    for k in node.value.keys
                    if isinstance(k, ast.Constant) and isinstance(k.value, str)
                }
                for key in sorted(keys & RESERVED):
                    found.append(f"{path.relative_to(ROOT)}:{node.lineno} {key}")
    return found


def test_log_extra_keys_do_not_overwrite_log_record() -> None:
    assert collisions() == []


def test_reserved_names_include_the_original_bug() -> None:
    assert "created" in RESERVED
