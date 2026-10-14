from datetime import UTC, date, datetime
from typing import Any

import pytest

from adapters.alphavantage.models import AvEstimate
from adapters.errors import DataError
from agents.consensus.agent import ConsensusAgentPlugin
from core.config import load_config
from core.registry.protocols import EventContext

SETTINGS = load_config().thresholds.agents.consensus


def estimate(day: date, horizon: str = "fiscal quarter", **values: Any) -> AvEstimate:
    return AvEstimate.model_validate({"date": day, "horizon": horizon, **values})


class Source:
    def __init__(self, rows: list[AvEstimate]) -> None:
        self.rows = rows

    def earnings_estimates(self, symbol: str) -> list[AvEstimate]:
        return self.rows


def ctx() -> EventContext:
    return EventContext(
        event_id=1,
        ticker="NFLX",
        report_date=date(2026, 10, 20),
        report_time="AMC",
        stage="T-10",
        as_of=datetime(2026, 10, 9, 11, tzinfo=UTC),
    )


QUARTER = estimate(
    date(2026, 9, 30),
    eps_estimate_average="2.00",
    eps_estimate_high="2.20",
    eps_estimate_low="1.80",
    eps_estimate_analyst_count="20",
    eps_estimate_average_7_days_ago="1.96",
    eps_estimate_average_90_days_ago="1.60",
    eps_estimate_revision_up_trailing_30_days="5",
    eps_estimate_revision_down_trailing_30_days=None,
)


def test_features_by_hand_for_report_quarter() -> None:
    rows = [
        estimate(date(2026, 12, 31), eps_estimate_average="9.0"),  # следующий квартал — не тот
        estimate(date(2026, 12, 31), "fiscal year", eps_estimate_average="8.0"),
        QUARTER,
        estimate(date(2026, 6, 30), eps_estimate_average="1.0"),  # прошлый — старее
    ]
    f = ConsensusAgentPlugin(Source(rows), SETTINGS).run(ctx())
    assert f.revision_trend_7_90 == pytest.approx((2.00 - 1.60) / 1.60)  # +25%
    assert f.revision_trend_7d == pytest.approx((2.00 - 1.96) / 1.96)
    assert f.estimate_dispersion == pytest.approx(0.40 / 2.00)
    assert f.revisions_net_30d == pytest.approx(5 / 20)  # пропуск «вниз» — 0 пересмотров
    assert f.analyst_count == 20


def test_eps_near_zero_uses_floor() -> None:
    row = estimate(
        date(2026, 9, 30), eps_estimate_average="0.03", eps_estimate_average_90_days_ago="0.01"
    )
    f = ConsensusAgentPlugin(Source([row]), SETTINGS).run(ctx())
    assert f.revision_trend_7_90 == pytest.approx(0.02 / 0.05)  # знаменатель не меньше $0,05
    assert (f.estimate_dispersion, f.revisions_net_30d) == (None, None)


def test_no_quarter_for_report_is_data_error() -> None:
    stale = estimate(date(2026, 3, 31), eps_estimate_average="1.0")  # старше 120 дней
    with pytest.raises(DataError, match="no quarter estimate"):
        ConsensusAgentPlugin(Source([stale]), SETTINGS).run(ctx())
