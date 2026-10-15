import pytest

from core.text import plural


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (1, "сделка"),
        (2, "сделки"),
        (4, "сделки"),
        (5, "сделок"),
        (11, "сделок"),
        (12, "сделок"),
        (21, "сделка"),
        (22, "сделки"),
        (111, "сделок"),
        (0, "сделок"),
    ],
)
def test_plural(n: int, expected: str) -> None:
    assert plural(n, "сделка", "сделки", "сделок") == expected
