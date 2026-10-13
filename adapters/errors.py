"""Ошибки источников данных (SPEC §6, §13)."""


class DataError(Exception):
    """Источник не дал нужных данных. Решение получает код DATA_*, сигнал не выдаётся."""

    def __init__(self, source: str, detail: str) -> None:
        super().__init__(f"{source}: {detail}")
        self.source = source
        self.detail = detail
