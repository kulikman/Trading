"""Рыночные эталоны SPEC §9: с чем сравнивается прогноз модели (edge = p_model − p_market).

- p_beat — вероятность рынка предсказаний (Polymarket); рынка нет — эталона нет, edge не считается.
- move_ratio — 0,5.
- p_up — «0,5 с поправкой на skew_25d»: цифровой колл со страйком у цены, P(S_T > S) =
  N(d2) − S·φ(d1)·√T·∂σ/∂K. При d1, d2 ≈ 0 (короткий срок, ATM) N(d2) ≈ 0,5, φ(d1) ≈ φ(0).
  Наклон улыбки по 25Δ-страйкам: ∂σ/∂K ≈ −skew_25d / (K_call25 − K_put25), а расстояние
  K_call25 − K_put25 ≈ 2·z25·σ·√T·S, z25 = Φ⁻¹(0,75). Отсюда
  P_up ≈ 0,5 + φ(0) / (2·z25) · skew_25d / σ_ATM ≈ 0,5 + 0,296 · skew_25d / σ_ATM.
  Путы дороже коллов (skew > 0) — рынок закладывает чаще небольшой рост и редкое сильное падение.
"""

import math
from statistics import NormalDist

from models.logistic import clip

MOVE_RATIO_MARKET = 0.5
NEUTRAL_UP = 0.5
SKEW_COEFFICIENT = NormalDist().pdf(0.0) / (2 * NormalDist().inv_cdf(0.75))  # ≈ 0,296


def market_p_up(skew_25d: float | None, atm_iv: float | None, margin: float) -> float:
    """Рыночная вероятность роста; без skew или IV — 0,5."""
    if skew_25d is None or atm_iv is None or not atm_iv > 0 or not math.isfinite(skew_25d):
        return NEUTRAL_UP
    return clip(NEUTRAL_UP + SKEW_COEFFICIENT * skew_25d / atm_iv, margin)
