"""Прогноз события на стадии (T15, SPEC §9): три вероятности, рыночные эталоны и edge.

Задачи расписания `forecast` (T−7, T−3) и `final_forecast` (T−1) пишут строку `forecast` с
версией действующих моделей. Повтор на той же стадии и версии не перезаписывает строку.
"""

from functools import partial

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.config.registry import Registry
from core.config.thresholds import Models
from core.db import models as orm
from core.domain.earnings import Forecast
from core.domain.schedule import EventJob
from core.registry.agent_jobs import feature_stage
from core.scheduler.dispatch import Handler
from models.features import stage_features
from models.logistic import clip, predict
from models.market import MOVE_RATIO_MARKET, market_p_up
from models.versions import active_models

FORECAST_JOBS = ("forecast", "final_forecast")
MARKET_P_BEAT = "polymarket.pm_p_beat"  # рынок предсказаний — после Polymarket (отложен)


def run_forecast(
    session: Session, job: EventJob, *, registry: Registry, settings: Models
) -> Forecast:
    """Прогноз по признакам стадии; сохраняется один раз на (событие, стадия, версия)."""
    stage = feature_stage(job.stage)
    features = stage_features(session, job.event_id, stage, registry)
    models = active_models(session)
    margin = settings.probability_clip
    p_beat = clip(predict(models.params["p_beat"], features), margin)
    p_up = clip(predict(models.params["p_up"], features), margin)
    move = clip(predict(models.params["move_ratio"], features), margin)
    market_beat = features.get(MARKET_P_BEAT)
    market_up = market_p_up(
        features.get("options.skew_25d"), features.get("options.atm_iv"), margin
    )
    forecast = Forecast(
        event_id=job.event_id,
        stage=stage,
        model_version=models.version,
        p_beat=p_beat,
        p_up=p_up,
        move_ratio=move,
        market_p_beat=market_beat,
        market_p_up=market_up,
        implied_move=features.get("options.implied_move"),
        edge_beat=None if market_beat is None else p_beat - market_beat,
        edge_up=p_up - market_up,
        edge_move=move - MOVE_RATIO_MARKET,
    )
    session.execute(
        insert(orm.Forecast)
        .values(forecast.model_dump())
        .on_conflict_do_nothing(index_elements=["event_id", "stage", "model_version"])
    )
    return forecast


def forecast_handlers(registry: Registry, settings: Models) -> dict[str, Handler]:
    """Обработчики диспетчера для задач прогноза."""

    handle = partial(_handle, registry=registry, settings=settings)
    return dict.fromkeys(FORECAST_JOBS, handle)


def _handle(session: Session, job: EventJob, *, registry: Registry, settings: Models) -> None:
    run_forecast(session, job, registry=registry, settings=settings)
