"""Строки в списке, записанные подряд без запятой, — только в скобках.

Неявная склейка соседних строк в списке неотличима от пропущенной запятой (замечание CodeQL
«Implicit string concatenation in a list»); дважды появлялась в backtest/report.py.
"""

import io
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIRS = ("adapters", "agents", "backtest", "core", "execution", "notify")
STRING_START = {tokenize.STRING, tokenize.FSTRING_START}
STRING_END = {tokenize.STRING, tokenize.FSTRING_END}
SKIP = {tokenize.NL, tokenize.NEWLINE, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT}


def implicit_concatenations(source: str) -> list[int]:
    """Строки, где строковый литерал в списке продолжает предыдущий без запятой."""
    found, brackets, previous_is_string = [], [], False
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in SKIP:
            continue
        if token.type == tokenize.OP and token.string in "([{":
            brackets.append(token.string)
        elif token.type == tokenize.OP and token.string in ")]}":
            brackets.pop()
        if token.type in STRING_START and previous_is_string and brackets[-1:] == ["["]:
            found.append(token.start[0])
        previous_is_string = token.type in STRING_END
    return found


def test_no_implicit_string_concatenation_in_lists() -> None:
    problems = [
        f"{path.relative_to(ROOT)}:{line}"
        for folder in SOURCE_DIRS
        for path in sorted((ROOT / folder).rglob("*.py"))
        for line in implicit_concatenations(path.read_text(encoding="utf-8"))
    ]
    assert problems == []


def test_detector_finds_the_case_and_ignores_parentheses() -> None:
    assert implicit_concatenations('x = [\n    "a"\n    "b",\n]\n') == [3]
    assert implicit_concatenations('x = [\n    (\n        "a"\n        "b"\n    ),\n]\n') == []
    assert implicit_concatenations('x = [\n    f"a{1}"\n    "b",\n]\n') == [3]
