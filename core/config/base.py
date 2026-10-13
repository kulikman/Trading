"""Общая база конфигурационных моделей."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Fraction = Annotated[float, Field(ge=0, le=1)]
PositiveFloat = Annotated[float, Field(gt=0)]
PositiveInt = Annotated[int, Field(gt=0)]


class StrictModel(BaseModel):
    """Неизвестный ключ — ошибка: опечатка в YAML не должна молча превращаться в «нет порога»."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
