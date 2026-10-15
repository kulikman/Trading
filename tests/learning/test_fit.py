import random

import pytest

from learning.fit import brier, fit_logistic, fit_platt, robust_scale
from models.logistic import ModelParams


def test_logistic_learns_signal_and_beats_constant() -> None:
    rng = random.Random(7)  # noqa: S311 — детерминированные данные теста, не криптография
    rows, labels = [], []
    for _ in range(200):
        x = rng.uniform(-1, 1)
        rows.append({"options.skew_25d": x, "noise.x": rng.uniform(-1, 1)})
        labels.append(int(rng.random() < (0.85 if x > 0 else 0.15)))
    params = fit_platt(
        fit_logistic(rows, labels, ["options.skew_25d", "noise.x"], {}), rows, labels
    )
    assert params.betas["options.skew_25d"] > 1.0  # сигнал найден
    assert abs(params.betas["noise.x"]) < 0.5  # шум — около нуля
    constant = ModelParams(intercept=0.0)
    assert brier(params, rows, labels) < brier(constant, rows, labels) - 0.05


def test_missing_feature_is_neutral_and_scales() -> None:
    params = fit_logistic([{}, {}], [1, 0], ["a.b"], {"a.b": 2.0})
    assert params.scales == {"a.b": 2.0}
    assert params.betas["a.b"] == pytest.approx(0.0)  # признака нет ни разу — веса нет
    assert robust_scale([0.0, 1.0, -3.0, 2.0]) == 4.0  # медиана |x| (2) × 2
    assert robust_scale([]) == 1.0
