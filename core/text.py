"""Русский текст для людей: согласование числительного с существительным."""


def plural(n: int, one: str, few: str, many: str) -> str:
    """«1 сделка», «2 сделки», «5 сделок»: форма по последним цифрам числа."""
    tail = abs(n) % 100
    if 11 <= tail <= 14:
        return many
    last = tail % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many
