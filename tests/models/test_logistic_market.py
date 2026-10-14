import math

import pytest

from models.logistic import ModelParams, clip, logit, predict, sigmoid
from models.market import SKEW_COEFFICIENT, market_p_up


def test_predict_scales_clips_and_skips_missing() -> None:
    params = ModelParams(
        intercept=0.0,
        betas={"a.x": 2.0, "a.y": -1.0, "a.missing": 5.0},
        scales={"a.x": 0.10, "a.y": 1.0},
    )
    # x = 0.05 / 0.10 = 0.5 → 2·0.5 = 1; y = 3 → обрезка до 1 → −1; нет признака — 0
    assert predict(params, {"a.x": 0.05, "a.y": 3.0}) == pytest.approx(sigmoid(0.0))
    assert predict(params, {"a.x": 0.05}) == pytest.approx(sigmoid(1.0))
    assert predict(params, {"a.x": math.nan}) == pytest.approx(0.5)


def test_platt_calibration_and_helpers() -> None:
    params = ModelParams(intercept=1.0, platt_a=0.5, platt_b=-0.5)
    assert predict(params, {}) == pytest.approx(sigmoid(0.5 * 1.0 - 0.5))
    assert logit(sigmoid(0.7)) == pytest.approx(0.7)
    assert sigmoid(-50) == pytest.approx(1.9e-22, rel=0.1)  # без переполнения
    assert (clip(0.999, 0.02), clip(0.001, 0.02), clip(0.4, 0.02)) == (0.98, 0.02, 0.4)


def test_market_p_up_digital_skew_correction() -> None:
    # φ(0) / (2·Φ⁻¹(0,75)) = 0,3989 / 1,3490 ≈ 0,2957
    assert pytest.approx(0.2957, abs=1e-4) == SKEW_COEFFICIENT
    assert market_p_up(0.03, 0.60, 0.02) == pytest.approx(0.5 + SKEW_COEFFICIENT * 0.05)
    assert market_p_up(None, 0.60, 0.02) == 0.5
    assert market_p_up(0.03, 0.0, 0.02) == 0.5
    assert market_p_up(5.0, 0.10, 0.02) == 0.98  # обрезка
