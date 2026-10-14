from datetime import UTC, date, datetime, time

import pytest

from core.config import load_config
from core.config.schedule import EventJobSpec
from core.domain.schedule import EventJob
from core.scheduler.plan import job_key, plan_event_jobs
from core.session_guard import ET

SPECS = load_config().schedule.event_jobs


def by_key(jobs: list[EventJob]) -> dict[tuple[str, str], EventJob]:
    return {(j.stage, j.job): j for j in jobs}


def et(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), tzinfo=ET).astimezone(UTC)


def test_bmo_tuesday_timeline() -> None:
    jobs = by_key(plan_event_jobs(1, date(2026, 10, 20), "BMO", SPECS))
    assert len(jobs) == len(SPECS)
    assert jobs[("T-14", "sector_cycle")].run_at == et(date(2026, 10, 6), 7)
    assert jobs[("T-1", "mode_b_entry")].run_at == et(date(2026, 10, 19), 15, 30)
    assert jobs[("T0", "stop_gap")].run_at == et(date(2026, 10, 20), 9, 30)
    assert jobs[("T+1", "outcome")].run_at == et(date(2026, 10, 21), 8)
    assert not any(j.outside_session for j in jobs.values())


def test_amc_timeline_anchors_on_reaction_day() -> None:
    jobs = by_key(plan_event_jobs(1, date(2026, 10, 15), "AMC", SPECS))  # четверг после закрытия
    # вход через отчёт — в день отчёта до публикации, реакция и закрытие — на следующий день
    assert jobs[("T-1", "mode_b_entry")].run_at == et(date(2026, 10, 15), 15, 30)
    assert jobs[("T0", "parse_report")].run_at == et(date(2026, 10, 16), 7, 30)
    assert jobs[("T0", "close_positions")].run_at == et(date(2026, 10, 16), 10, 45)


def test_monday_report_moves_pre_report_jobs_to_friday() -> None:
    jobs = by_key(plan_event_jobs(1, date(2026, 10, 19), "BMO", SPECS))
    friday = date(2026, 10, 16)
    assert jobs[("T-1", "mode_b_entry")].run_at == et(friday, 15, 30)  # не после отчёта
    assert jobs[("T-1", "mode_a_exit")].run_at == et(friday, 15, 50)
    assert jobs[("T-1", "final_forecast")].run_at == et(friday, 15, 5)
    assert jobs[("T-10", "dossier")].run_at == et(date(2026, 10, 9), 7)


def test_default_shift_rule_analysis_back_execution_forward() -> None:
    specs = [
        EventJobSpec(stage="T+1", job="review", offset_days=1, time_et=time(8), kind="analysis"),
        EventJobSpec(stage="T+1", job="trail", offset_days=1, time_et=time(10), kind="execution"),
    ]
    jobs = by_key(plan_event_jobs(1, date(2026, 11, 25), "BMO", specs))  # +1 — Thanksgiving
    assert jobs[("T+1", "review")].run_at.astimezone(ET).date() == date(2026, 11, 25)
    assert jobs[("T+1", "trail")].run_at.astimezone(ET).date() == date(2026, 11, 27)


def test_execution_after_early_close_is_flagged() -> None:
    jobs = by_key(
        plan_event_jobs(1, date(2026, 11, 30), "BMO", SPECS)
    )  # T−1 → пятница 27.11, 13:00
    entry = jobs[("T-1", "mode_b_entry")]
    assert entry.run_at == et(date(2026, 11, 27), 15, 30)
    assert entry.outside_session is True
    assert jobs[("T-1", "mode_a_exit")].outside_session is True
    assert jobs[("T-1", "final_forecast")].outside_session is False  # анализ не помечается


def test_dst_change_keeps_et_wall_clock() -> None:
    jobs = by_key(plan_event_jobs(1, date(2026, 11, 2), "BMO", SPECS))
    assert jobs[("T-1", "mode_b_entry")].run_at == datetime(2026, 10, 30, 19, 30, tzinfo=UTC)  # EDT
    assert jobs[("T0", "stop_gap")].run_at == datetime(2026, 11, 2, 14, 30, tzinfo=UTC)  # EST


def test_unknown_time_plans_as_bmo() -> None:
    unknown = by_key(plan_event_jobs(1, date(2026, 10, 20), None, SPECS))
    bmo = by_key(plan_event_jobs(1, date(2026, 10, 20), "BMO", SPECS))
    assert {k: j.run_at for k, j in unknown.items()} == {k: j.run_at for k, j in bmo.items()}


def test_job_key() -> None:
    assert job_key(7, "T-1", "mode_b_entry") == "event:7:T-1:mode_b_entry"


@pytest.mark.parametrize("stage", ["T-x", "T", "t-1", "T+"])
def test_bad_stage_rejected(stage: str) -> None:
    with pytest.raises(ValueError, match="stage"):
        EventJobSpec(stage=stage, job="x", offset_days=0, time_et=time(9), kind="analysis")
