from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import load_config
from core.db import models as orm
from core.db.store import save_reported_earnings, set_implied_move, sync_universe, update_earnings
from core.domain.earnings import ReportedEarnings
from core.domain.schedule import EventJob
from core.registry.state import sync_plugins
from learning.season import learn_season
from models.forecast import run_forecast
from models.versions import active_models, exploration_models, init_prior

CONFIG = load_config()
NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)


def seed(
    session: Session, count: int, *, predictive: bool = True, ticker: str = "NFLX"
) -> list[int]:
    """count прошлых отчётов: рост цены там, где skew_25d отрицательный (предсказуемо)."""
    sync_universe(session, CONFIG.universe)
    sync_plugins(session, CONFIG.registry)
    ids = []
    for i in range(count):
        day = date(2021, 11, 1) + timedelta(days=29 * i)
        skew = -0.08 if i % 2 == 0 else 0.08
        up = (skew < 0) if predictive else (i % 3 == 0)
        save_reported_earnings(
            session,
            [
                ReportedEarnings(
                    ticker=ticker,
                    report_date=day,
                    report_time="BMO",
                    fiscal_period_end=day - timedelta(days=20),
                    eps_consensus=1.0,
                    eps_actual=1.1 if up else 0.9,
                )
            ],
        )
        set_implied_move(session, ticker, day, 0.05)
        update_earnings(session, ticker, day, {"actual_move": 0.06 if up else -0.06})
        event = orm.Event(
            ticker=ticker, report_date=day, report_time="BMO", date_status="confirmed"
        )
        session.add(event)
        session.flush()
        session.add(
            orm.FeatureSnapshot(
                event_id=event.id,
                stage="T-1",
                agent_id="options",
                agent_version="0.1.0",
                features={"skew_25d": skew, "implied_move": 0.05},
            )
        )
        ids.append(event.id)
    session.flush()
    init_prior(
        session, CONFIG.thresholds.models, today=date(2026, 10, 15), now=NOW - timedelta(days=1)
    )
    return ids


def test_season_accepts_better_version(session: Session, tmp_path: Path) -> None:
    seed(session, 60)
    result = learn_season(session, CONFIG, NOW, tmp_path)
    assert result.version == "0.2.0"
    assert result.accepted, result.reason
    by_model = {o.model: o for o in result.models}
    assert by_model["p_up"].improved
    new, old = by_model["p_up"].brier_new, by_model["p_up"].brier_old
    assert new is not None
    assert old is not None
    assert new < old
    assert active_models(session).version == "0.2.0"
    assert exploration_models(session) is None  # принятая — исследовать нечего
    assert result.contributions["options"] > 0  # без опционов хуже
    assert result.theta.startswith("мало сделок")  # правило 30 для θ и Келли
    report = (tmp_path / "season_0.2.0.md").read_text()
    assert "**Решение:** принята" in report


def test_small_season_creates_no_version(session: Session, tmp_path: Path) -> None:
    seed(session, 10)
    result = learn_season(session, CONFIG, NOW, tmp_path)
    assert not result.accepted
    assert result.reason.startswith("мало данных — версия не создана")
    assert "мало наблюдений: 10 из 30" in result.reason
    assert active_models(session).version == "0.1.0"  # действующая не меняется
    assert exploration_models(session) is None  # исследовать нечего
    assert (tmp_path / "season_0.2.0.md").exists()  # отчёт всё равно есть


def test_rejected_version_is_explored_on_every_fifth_event(session: Session) -> None:
    ids = seed(session, 10)
    for name in ("p_beat", "p_up", "move_ratio"):
        session.add(
            orm.ModelVersion(
                model=name,
                version="0.2.0",
                params={"intercept": 2.0},
                trained_at=NOW,
                accepted=False,
                reason="test: не лучше действующей",
            )
        )
    session.flush()
    explored = exploration_models(session)
    assert explored is not None
    assert explored.version == "0.2.0"
    for event_id in ids:
        job = EventJob(
            event_id=event_id, stage="T-1", job="final_forecast", kind="analysis", run_at=NOW
        )
        forecast = run_forecast(
            session, job, registry=CONFIG.registry, settings=CONFIG.thresholds.models
        )
        expected = event_id % 5 == 0
        assert forecast.exploration is expected
        assert forecast.model_version == ("0.2.0" if expected else "0.1.0")


def test_quarantine_by_company_brier(session: Session) -> None:
    ids = seed(session, 8, predictive=False, ticker="TSLA")
    for event_id in ids:  # система уверенно ждала роста — а рост был лишь в 3 из 8
        session.add(orm.Forecast(event_id=event_id, stage="T-1", model_version="0.1.0", p_up=0.95))
    session.flush()
    result = learn_season(session, CONFIG, NOW)
    assert "TSLA" in result.quarantine
    company = session.get(orm.Company, "TSLA")
    assert company is not None
    assert company.calibration_status == "quarantine"
    stored = session.scalars(select(orm.ModelVersion.version).distinct()).all()
    assert sorted(stored) == ["0.1.0"]  # 8 отчётов — мало для версии, карантин всё равно считается
