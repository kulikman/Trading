"""Общая база моделей ответов внешних API и чтение ключей из окружения."""

import os
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from core.config import ConfigError

BLANK_VALUES = frozenset({"", "None", "-"})


class ApiModel(BaseModel):
    """Новые поля API не ломают разбор; неизвестные поля отбрасываются."""

    model_config = ConfigDict(extra="ignore", frozen=True, populate_by_name=True)


class BlankAsNoneModel(ApiModel):
    """Для API, где «нет значения» приходит строкой: "", "None", "-" (Alpha Vantage)."""

    @model_validator(mode="before")
    @classmethod
    def _blank_to_none(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {
                k: (None if isinstance(v, str) and v.strip() in BLANK_VALUES else v)
                for k, v in data.items()
            }
        return data


def require_env(name: str) -> str:
    """Секрет из переменной окружения. В логи и LLM не передаётся."""
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"{name} is not set")
    return value
