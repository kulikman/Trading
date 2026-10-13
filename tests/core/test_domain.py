from datetime import UTC, date, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from core.domain.earnings import Event, FeatureSnapshot, Forecast
from core.domain.market import PeerEdge
from core.domain.trading import Decision, TradeCardTransition

AWARE = datetime(2026, 10, 13, 13, 30, tzinfo=UTC)
NAIVE = datetime(2026, 10, 13, 13, 30)  # noqa: DTZ001 — the point of the test


def _decision(**overrides: Any) -> Decision:
    fields: dict[str, Any] = {"event_id": 1, "status": "SKIPPED", "reasons": ["EDGE_LOW"]}
    fields["decided_at"] = AWARE
    return Decision(**(fields | overrides))


def test_valid_skipped_decision() -> None:
    assert _decision().reasons == ["EDGE_LOW"]


def test_naive_datetime_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        _decision(decided_at=NAIVE)
    with pytest.raises(ValidationError, match="timezone"):
        TradeCardTransition(card_id=1, at=NAIVE, to_state="ARMED")


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"reasons": []}, "SKIPPED decision needs at least one reason"),
        ({"status": "DATA_FAIL", "reasons": ["EDGE_LOW"]}, "DATA_\\* code as the main reason"),
        ({"status": "ENTERED", "reasons": []}, "needs strategy_id and construction"),
        ({"reasons": ["NOT_A_CODE"]}, "reasons.0"),
        ({"status": "MAYBE"}, "status"),
    ],
)
def test_inconsistent_decision_rejected(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        _decision(**overrides)


def test_data_fail_with_data_code_is_valid() -> None:
    decision = _decision(status="DATA_FAIL", reasons=["DATA_MASSIVE", "LIQUIDITY"])
    assert decision.reasons[0] == "DATA_MASSIVE"


def test_confirmed_event_needs_two_date_sources() -> None:
    one_source = [{"source": "benzinga", "date": "2026-10-14"}]
    with pytest.raises(ValidationError, match="at least 2 date_sources"):
        Event(
            ticker="GS",
            report_date=date(2026, 10, 14),
            date_status="confirmed",
            date_sources=one_source,
        )
    projected = Event(
        ticker="GS",
        report_date=date(2026, 10, 14),
        date_status="projected",
        date_sources=one_source,
    )
    assert projected.queue_status == "planned"


def test_forecast_probability_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError, match="p_up"):
        Forecast(event_id=1, stage="T-3", model_version="0.1.0", p_up=1.2)


def test_features_must_be_numeric() -> None:
    with pytest.raises(ValidationError, match="features"):
        FeatureSnapshot.model_validate(
            {
                "event_id": 1,
                "stage": "T-7",
                "agent_id": "macro",
                "agent_version": "0.1.0",
                "features": {"regime": "risk-on"},
            }
        )


def test_peer_edge_cannot_point_to_itself() -> None:
    with pytest.raises(ValidationError, match="itself"):
        PeerEdge(from_ticker="JPM", to_ticker="JPM")
