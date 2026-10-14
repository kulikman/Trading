from datetime import date

import pytest
from sqlalchemy.orm import Session

from adapters.alphavantage.mapping import reported_earnings
from adapters.alphavantage.models import AvEarnings
from backtest.archive_steps import DateCheck, match_period
from core.db.store import update_earnings

PERIODS = [date(2025, 9, 27), date(2025, 12, 27), date(2026, 1, 3)]


def test_match_period_nearest_within_tolerance() -> None:
    assert match_period(date(2025, 9, 30), PERIODS, 7) == date(2025, 9, 27)
    assert match_period(date(2025, 12, 31), PERIODS, 7) == date(2026, 1, 3)  # 3 дня ближе 4
    assert match_period(date(2026, 3, 31), PERIODS, 7) is None


def test_match_period_tie_takes_earlier() -> None:
    assert match_period(date(2025, 12, 30), [date(2025, 12, 27), date(2026, 1, 2)], 7) == date(
        2025, 12, 27
    )


def test_date_check_shift() -> None:
    check = DateCheck("C", date(2025, 11, 6), date(2025, 10, 14), "mismatch")
    assert check.shift_days == -23
    assert DateCheck("C", date(2025, 11, 6), None, "no_8k").shift_days is None


def test_update_earnings_rejects_non_archive_fields() -> None:
    with pytest.raises(ValueError, match="not archive fields"):
        update_earnings(Session(), "NFLX", date(2026, 1, 20), {"eps_actual": 1.0})


def test_reported_earnings_skips_rows_without_date_and_sorts() -> None:
    history = AvEarnings.model_validate(
        {
            "symbol": "IBM",
            "quarterlyEarnings": [
                {
                    "fiscalDateEnding": "2026-06-30",
                    "reportedDate": "2026-07-22",
                    "reportedEPS": "2.9",
                    "estimatedEPS": "2.8",
                    "surprisePercentage": "3.5",
                    "reportTime": "post-market",
                },
                {"fiscalDateEnding": "2026-09-30", "reportedDate": "None"},
                {
                    "fiscalDateEnding": "2026-03-31",
                    "reportedDate": "2026-04-21",
                    "reportedEPS": "None",
                },
            ],
        }
    )
    rows = reported_earnings(history)
    assert [(r.report_date, r.report_time, r.eps_actual) for r in rows] == [
        (date(2026, 4, 21), None, None),
        (date(2026, 7, 22), "AMC", 2.9),
    ]
    assert rows[1].eps_surprise_pct == 3.5
