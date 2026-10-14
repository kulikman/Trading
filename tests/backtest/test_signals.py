from datetime import date

import pytest

from backtest.signals import Signal, condor_strikes, signals
from core.config import load_config
from core.domain.earnings import EarningsTrack

THRESHOLDS = load_config().thresholds
SINCE, TODAY = date(2024, 10, 14), date(2026, 10, 14)


def row(
    day: date, move: float | None, implied: float | None = None, check: str | None = "ok"
) -> EarningsTrack:
    return EarningsTrack.model_validate(
        {
            "ticker": "NFLX",
            "report_date": day,
            "report_time": "AMC",
            "actual_move": move,
            "implied_move": implied,
            "date_check": check,
        }
    )


HISTORY = [row(date(2023, 1 + 3 * i, 18), m) for i, m in enumerate([0.10, -0.08, 0.12, -0.10])]


def run(rows: list[EarningsTrack]) -> list[Signal]:
    return signals(
        "NFLX",
        rows,
        since=SINCE,
        today=TODAY,
        settings=THRESHOLDS.backtest,
        constructions=THRESHOLDS.constructions,
    )


@pytest.mark.parametrize(
    ("implied", "construction", "reason"),
    [
        (0.06, "straddle", None),  # история 10% / 6% = 1,67 > 1,3
        (0.15, "iron_condor", None),  # 10% / 15% = 0,67 < 0,75
        (0.10, None, "neutral"),  # 1,0
    ],
)
def test_signal_by_historical_ratio(
    implied: float, construction: str | None, reason: str | None
) -> None:
    [signal] = run([*HISTORY, row(date(2025, 1, 21), 0.05, implied)])
    assert signal.history_move == pytest.approx(0.10)
    assert signal.ratio == pytest.approx(0.10 / implied)
    assert (signal.construction, signal.reason, signal.history_reports) == (construction, reason, 4)


def test_only_past_reports_feed_the_signal() -> None:
    later = row(date(2025, 4, 17), 0.50, 0.06)  # огромное движение позже — не влияет на январь
    first, second = run([*HISTORY, row(date(2025, 1, 21), 0.05, 0.06), later])
    assert first.history_move == pytest.approx(0.10)
    # окно — 8 последних отчётов: все 5 прошлых, включая январский
    assert second.history_move == pytest.approx((0.10 + 0.08 + 0.12 + 0.10 + 0.05) / 5)


def test_lookback_and_min_history() -> None:
    [signal] = run([*HISTORY[:3], row(date(2025, 1, 21), 0.05, 0.06)])
    assert (signal.construction, signal.reason, signal.history_reports) == (None, "no_history", 3)


def test_mismatched_dates_are_excluded_everywhere() -> None:
    rows = [
        *HISTORY[:3],
        row(date(2024, 1, 18), 0.90, check="mismatch"),
        row(date(2025, 1, 21), 0.05, 0.06),
    ]
    rows.append(row(date(2025, 4, 17), 0.05, 0.06, check="mismatch"))
    [signal] = run(rows)
    assert signal.reason == "no_history"  # строка с mismatch не считается историей


def test_events_outside_window_or_without_implied_are_skipped() -> None:
    rows = [*HISTORY, row(date(2024, 7, 18), 0.05, 0.06), row(date(2025, 1, 21), 0.05, None)]
    rows.append(row(date(2026, 10, 13), None, 0.06))  # реакция 14.10 — не раньше today
    assert run(rows) == []


def test_condor_strikes_nearest_listed() -> None:
    strikes = [80, 85, 90, 95, 100, 105, 110, 115, 120]
    chosen = condor_strikes(strikes, strikes, 100.0, 0.07, 1.0, 2.0)
    assert chosen is not None
    assert (chosen.long_put, chosen.short_put, chosen.short_call, chosen.long_call) == (
        85,
        95,
        105,
        115,
    )
    assert chosen.width == 10


def test_condor_wings_must_be_beyond_shorts() -> None:
    assert condor_strikes([105], [95, 90], 100.0, 0.05, 1.0, 2.0) is None  # нет длинного колла
    assert condor_strikes([95], [95], 100.0, 0.05, 1.0, 2.0) is None  # нет колла выше цены
