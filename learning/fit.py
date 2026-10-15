"""Обучение моделей SPEC §9 без внешних библиотек (T20): логистическая регрессия и Platt.

Признак xi = clip(значение / масштаб, −1, 1) — как в `models.logistic.predict`. Регрессия —
градиентный спуск с L2 (данных сотни, не миллионы). Platt: p' = σ(a·z + b), a и b — логистическая
регрессия меток на сырой логит модели. Brier — средний квадрат (p − y).
"""

import math
from collections.abc import Mapping, Sequence

from models.logistic import ModelParams, predict, sigmoid

ITERATIONS = 2000
LEARNING_RATE = 0.5
L2 = 0.01


def scaled(features: Mapping[str, float], name: str, scale: float) -> float:
    value = features.get(name)
    if value is None or not math.isfinite(value):
        return 0.0  # нет признака — нейтрально, как в predict
    return max(-1.0, min(1.0, value / scale))


def fit_logistic(
    rows: Sequence[Mapping[str, float]],
    labels: Sequence[int],
    names: Sequence[str],
    scales: Mapping[str, float],
) -> ModelParams:
    """β0 и β по признакам names; без калибровки (a = 1, b = 0)."""
    xs = [[scaled(r, n, scales.get(n, 1.0)) for n in names] for r in rows]
    weights, intercept = [0.0] * len(names), 0.0
    count = len(rows)
    for _ in range(ITERATIONS):
        grad_w, grad_b = [0.0] * len(names), 0.0
        for x, y in zip(xs, labels, strict=True):
            error = sigmoid(intercept + sum(w * v for w, v in zip(weights, x, strict=True))) - y
            grad_b += error
            for i, v in enumerate(x):
                grad_w[i] += error * v
        intercept -= LEARNING_RATE * grad_b / count
        weights = [
            w - LEARNING_RATE * (g / count + L2 * w) for w, g in zip(weights, grad_w, strict=True)
        ]
    return ModelParams(
        intercept=intercept,
        betas=dict(zip(names, weights, strict=True)),
        scales={n: scales.get(n, 1.0) for n in names},
    )


def fit_platt(
    params: ModelParams, rows: Sequence[Mapping[str, float]], labels: Sequence[int]
) -> ModelParams:
    """Калибровка Platt на выборке: a, b по сырому логиту модели."""
    raw = params.model_copy(update={"platt_a": 1.0, "platt_b": 0.0})
    logits = [_logit(predict(raw, r)) for r in rows]
    a, b = 1.0, 0.0
    count = len(rows)
    for _ in range(ITERATIONS):
        grad_a = grad_b = 0.0
        for z, y in zip(logits, labels, strict=True):
            error = sigmoid(a * z + b) - y
            grad_a += error * z
            grad_b += error
        a -= LEARNING_RATE * grad_a / count
        b -= LEARNING_RATE * grad_b / count
    return params.model_copy(update={"platt_a": a, "platt_b": b})


def brier(params: ModelParams, rows: Sequence[Mapping[str, float]], labels: Sequence[int]) -> float:
    """Средний квадрат ошибки вероятности."""
    return sum((predict(params, r) - y) ** 2 for r, y in zip(rows, labels, strict=True)) / len(rows)


def robust_scale(values: Sequence[float]) -> float:
    """Типичный размах признака без масштаба в конфиге: 2 × медиана |значения| (не ноль)."""
    sizes = sorted(abs(v) for v in values if math.isfinite(v) and v != 0)
    if not sizes:
        return 1.0
    return sizes[len(sizes) // 2] * 2 or 1.0


def _logit(p: float) -> float:
    p = min(max(p, 1e-9), 1 - 1e-9)
    return math.log(p / (1 - p))
