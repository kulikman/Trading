"""Общая база доменных моделей."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Probability = Annotated[float, Field(ge=0, le=1)]


class DomainModel(BaseModel):
    """Строгая неизменяемая модель; читается и из ORM-строки (from_attributes)."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, from_attributes=True)
