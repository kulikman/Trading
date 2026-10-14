"""Логистическая модель SPEC §9: logit(p) = β0 + Σ βi·xi, затем калибровка Platt.

Признак xi = clip(значение / масштаб, −1, 1): стартовые веса SPEC рассчитаны на соизмеримые
признаки. Нет признака — его вклад 0 (нейтрально). Калибровка Platt: p' = σ(a·logit(p) + b);
у стартовой версии a = 1, b = 0 (без поправки); изотоническую при 300+ наблюдениях добавит T20.
"""

import math
from collections.abc import Mapping

from pydantic import BaseModel, Field


class ModelParams(BaseModel):
    """Параметры одной модели, как они хранятся в model_version.params."""

    intercept: float
    betas: dict[str, float] = Field(default_factory=dict)  # «агент.признак» → β
    scales: dict[str, float] = Field(default_factory=dict)  # «агент.признак» → масштаб
    platt_a: float = 1.0
    platt_b: float = 0.0


def predict(params: ModelParams, features: Mapping[str, float]) -> float:
    """Откалиброванная вероятность по признакам «агент.признак»."""
    z = params.intercept
    for name, beta in params.betas.items():
        value = features.get(name)
        if value is None or not math.isfinite(value):
            continue
        scale = params.scales.get(name, 1.0)
        z += beta * max(-1.0, min(1.0, value / scale))
    return sigmoid(params.platt_a * z + params.platt_b)


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def logit(p: float) -> float:
    return math.log(p / (1.0 - p))


def clip(p: float, margin: float) -> float:
    return max(margin, min(1.0 - margin, p))
