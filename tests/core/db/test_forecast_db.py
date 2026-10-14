from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import load_config
from core.db import models as orm
from core.db.store import (
    save_reported_earnings,
    set_implied_move,
    sync_universe,
    update_earnings,
)
from core.domain.earnings import ReportedEarnings
from core.domain.schedule import EventJob
from core.registry.state import sync_plugins
from models.forecast import FORECAST_JOBS, forecast_handlers, run_forecast
from models.logistic import logit, sigmoid
from models.market import SKEW_COEFFICIENT
from models.versions import PRIOR_VERSION, NoModels, active_models, init_prior

CONFIG = load_config()
SETTINGS = CONFIG.thresholds.models
NOW = datetime(2026, 10, 14, 19, 10, tzinfo=UTC)  # T−7 15:10 ET
TODAY = date(2026, 10, 14)


def archive(session: Session) -> None:
    """4 прошлых отчёта: 3 побили консенсус (75%), 1 из 4 двинулся сильнее implied (25%)."""
    rows = [
        (date(2025, 10, 16), 1.0, 1.1, 0.05, 0.08),
        (date(2026, 1, 20), 1.0, 1.2, 0.05, 0.02),
        (date(2026, 4, 16), 1.0, 0.9, 0.05, -0.03),
        (date(2026, 7, 16), 1.0, 1.0, 0.05, 0.01),
    ]
    save_reported_earnings(
        session,
        [
            ReportedEarnings(
                ticker="NFLX",
                report_date=d,
                report_time="AMC",
                fiscal_period_end=d - timedelta(days=20),
                eps_consensus=consensus,
                eps_actual=actual,
            )
            for d, consensus, actual, _, _ in rows
        ],
    )
    for d, _, _, implied, move in rows:
        set_implied_move(session, "NFLX", d, implied)
        update_earnings(session, "NFLX", d, {"actual_move": move})


def snapshot(session: Session, event_id: int, stage: str, agent: str, **features: float) -> None:
    session.add(
        orm.FeatureSnapshot(
            event_id=event_id, stage=stage, agent_id=agent, agent_version="0.1.0", features=features
        )
    )


@pytest.fixture
def event(session: Session) -> int:
    sync_universe(session, CONFIG.universe)
    sync_plugins(session, CONFIG.registry)
    archive(session)
    row = orm.Event(
        ticker="NFLX", report_date=date(2026, 10, 20), report_time="AMC", date_status="confirmed"
    )
    session.add(row)
    session.flush()
    snapshot(session, row.id, "T-14", "sector", peer_surprise_mean=0.05, trend=1.0)
    snapshot(session, row.id, "T-7", "positioning", pre_run_3d=0.03, short_interest_days=2.0)
    snapshot(session, row.id, "T-7", "options", skew_25d=-0.03, atm_iv=0.6, implied_move=0.084)
    snapshot(
        session, row.id, "T-3", "options", skew_25d=0.09, atm_iv=0.6
    )  # позже — не видна на T−7
    session.flush()
    return row.id


def job(event_id: int, stage: str = "T-7", name: str = "forecast") -> EventJob:
    return EventJob(event_id=event_id, stage=stage, job=name, kind="analysis", run_at=NOW)


def test_prior_version_from_archive_base_rates(session: Session, event: int) -> None:
    assert init_prior(session, SETTINGS, today=TODAY, now=NOW)
    assert not init_prior(session, SETTINGS, today=TODAY, now=NOW)  # повтор ничего не меняет
    models = active_models(session)
    assert models.version == PRIOR_VERSION
    assert models.params["p_beat"].intercept == pytest.approx(logit(0.75))
    assert models.params["move_ratio"].intercept == pytest.approx(logit(0.25))
    p_up = models.params["p_up"]
    assert p_up.intercept == 0.0
    assert p_up.betas["dossier.disclosure"] == 2.0
    assert p_up.scales["positioning.pre_run_3d"] == 0.06


def test_forecast_by_hand_with_features_from_earlier_stages(session: Session, event: int) -> None:
    init_prior(session, SETTINGS, today=TODAY, now=NOW)
    forecast = run_forecast(session, job(event), registry=CONFIG.registry, settings=SETTINGS)
    # p_up: сектор с T−14 (сюрприз 0,05/0,10 → 0,5; тренд 1), позиционирование и опционы с T−7
    z = (
        1.2 * 0.5  # peer_surprise
        + 0.6 * 1.0  # sector_trend
        + 0.3 * 0.2  # short_interest 2 / 10
        - 0.5 * -0.3  # skew −0,03 / 0,10
        - 1.0 * 0.5  # pre_run 0,03 / 0,06
    )
    assert forecast.p_up == pytest.approx(sigmoid(z))
    assert forecast.market_p_up == pytest.approx(0.5 + SKEW_COEFFICIENT * (-0.03 / 0.6))
    assert forecast.market_p_up is not None
    assert forecast.edge_up == pytest.approx(sigmoid(z) - forecast.market_p_up)
    assert forecast.p_beat == pytest.approx(0.75)
    assert (forecast.market_p_beat, forecast.edge_beat) == (None, None)  # рынка предсказаний нет
    assert forecast.move_ratio == pytest.approx(0.25)
    assert forecast.edge_move == pytest.approx(0.0)  # эталон — частота архива 25% (решение 14.10)
    assert (forecast.implied_move, forecast.model_version) == (0.084, PRIOR_VERSION)
    run_forecast(session, job(event), registry=CONFIG.registry, settings=SETTINGS)  # повтор
    rows = session.scalars(select(orm.Forecast)).all()
    assert [(r.stage, r.model_version) for r in rows] == [("T-7", PRIOR_VERSION)]


def test_handlers_and_errors(session: Session, event: int) -> None:
    handlers = forecast_handlers(CONFIG.registry, SETTINGS)
    assert set(handlers) == set(FORECAST_JOBS) == {"forecast", "final_forecast"}
    with pytest.raises(NoModels, match="models-init"):
        handlers["forecast"](session, job(event))
    init_prior(session, SETTINGS, today=TODAY, now=NOW)
    handlers["final_forecast"](session, job(event, "T-1", "final_forecast"))
    stored = session.scalars(select(orm.Forecast)).one()
    assert stored.stage == "T-1"
    with pytest.raises(ValueError, match="no feature stage"):
        handlers["forecast"](session, job(event, "T+1"))


def test_prior_needs_archive(session: Session) -> None:
    with pytest.raises(NoModels, match="archive is empty"):
        init_prior(session, SETTINGS, today=TODAY, now=NOW)
