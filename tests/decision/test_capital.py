import pytest

from core.config import load_config
from core.registry.protocols import Proposal
from decision.capital import Rejection, Sizing, level_from_regime, size

THRESHOLDS = load_config().thresholds


def proposal(p: float, confidence: float | None = None, multiplier: float = 1.0) -> Proposal:
    return Proposal(
        strategy_id="iron_condor",
        mode="move",
        construction="iron_condor",
        edge=0.1,
        confidence=p if confidence is None else confidence,
        probability=p,
        cost_fraction=0.02,
        size_multiplier=multiplier,
    )


def test_kelly_eighth_in_seasons_1_2_and_quarter_after() -> None:
    early = size(proposal(0.64), level="green", b=1.0, seasons_1_2=True, thresholds=THRESHOLDS)
    later = size(proposal(0.64), level="green", b=1.0, seasons_1_2=False, thresholds=THRESHOLDS)
    assert isinstance(early, Sizing)
    assert isinstance(later, Sizing)
    assert early.risk_fraction == pytest.approx(0.125 * (0.64 - 0.36))  # ⅛ · (p·b − (1−p)) / b
    assert later.risk_fraction == pytest.approx(0.25 * 0.28)
    b2 = size(proposal(0.5), level="green", b=2.0, seasons_1_2=True, thresholds=THRESHOLDS)
    assert isinstance(b2, Sizing)
    assert b2.risk_fraction == pytest.approx(0.125 * (0.5 * 2 - 0.5) / 2)


def test_black_swan_levels_and_strategy_multiplier() -> None:
    yellow = size(
        proposal(0.64, multiplier=0.5),
        level="yellow",
        b=1.0,
        seasons_1_2=True,
        thresholds=THRESHOLDS,
    )
    assert isinstance(yellow, Sizing)
    assert yellow.risk_fraction == pytest.approx(0.125 * 0.28 * 0.7 * 0.5)
    low = size(proposal(0.64), level="orange", b=1.0, seasons_1_2=True, thresholds=THRESHOLDS)
    assert low == Rejection(["MACRO_BLOCK"])  # оранжевый — только уверенность > 0,8
    sure = size(proposal(0.85), level="orange", b=1.0, seasons_1_2=True, thresholds=THRESHOLDS)
    assert isinstance(sure, Sizing)
    assert sure.risk_fraction == pytest.approx(0.125 * 0.70 * 0.4)
    red = size(proposal(0.9), level="red", b=1.0, seasons_1_2=True, thresholds=THRESHOLDS)
    assert red == Rejection(["MACRO_BLOCK"])


def test_manual_red_and_no_edge() -> None:
    manual = THRESHOLDS.model_copy(
        update={
            "risk_limits": THRESHOLDS.risk_limits.model_copy(
                update={
                    "black_swan": THRESHOLDS.risk_limits.black_swan.model_copy(
                        update={"manual_red": True}
                    )
                }
            )
        }
    )
    assert size(
        proposal(0.9), level="green", b=1.0, seasons_1_2=True, thresholds=manual
    ) == Rejection(["MACRO_BLOCK"])
    assert size(
        proposal(0.5), level="green", b=1.0, seasons_1_2=True, thresholds=THRESHOLDS
    ) == Rejection(["EDGE_LOW"])


def test_level_from_regime() -> None:
    assert [level_from_regime(r) for r in (None, 0, 1, 2, 3, 7)] == [
        "green",
        "green",
        "yellow",
        "orange",
        "red",
        "red",
    ]
