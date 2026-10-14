"""Версии моделей: стартовая версия (до первого learn season) и выбор действующей.

Стартовая версия «0.1.0» (SPEC §9):
- p_up — веса SPEC «только до первого обучения» (thresholds.yaml: models.p_up_initial_betas
  и p_up_feature_map), свободный член 0 (без признаков — 0,5);
- p_beat и move_ratio — весов в SPEC нет, поэтому только свободный член: logit частоты события
  в архиве earnings_track за prior_lookback_days (EPS ≥ консенсуса; |движение| > implied move).
Действующая версия — последняя принятая; T20 (`learn season`) добавляет новые.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from core.config.thresholds import Models
from core.db import models as orm
from core.domain.types import ModelName
from models.logistic import ModelParams, clip, logit

PRIOR_VERSION = "0.1.0"
MODEL_NAMES: tuple[ModelName, ...] = ("p_beat", "p_up", "move_ratio")


@dataclass(frozen=True)
class ActiveModels:
    version: str
    params: Mapping[ModelName, ModelParams]


class NoModels(LookupError):
    """Моделей нет — сначала `make models-init`."""


def init_prior(session: Session, settings: Models, *, today: date, now: datetime) -> bool:
    """Создать стартовую версию, если версий ещё нет. False — уже есть."""
    if session.scalar(select(func.count()).select_from(orm.ModelVersion)):
        return False
    since = today - timedelta(days=settings.prior_lookback_days)
    track = orm.EarningsTrack
    beat_n, beat_rate = session.execute(
        select(
            func.count(),
            func.avg(case((track.eps_actual >= track.eps_consensus, 1.0), else_=0.0)),
        ).where(
            track.eps_actual.is_not(None),
            track.eps_consensus.is_not(None),
            track.report_date >= since,
            track.date_check.is_distinct_from("mismatch"),
        )
    ).one()
    move_n, move_rate = session.execute(
        select(
            func.count(),
            func.avg(case((func.abs(track.actual_move) > track.implied_move, 1.0), else_=0.0)),
        ).where(
            track.actual_move.is_not(None),
            track.implied_move.is_not(None),
            track.report_date >= since,
            track.date_check.is_distinct_from("mismatch"),
        )
    ).one()
    if not beat_n or not move_n:
        raise NoModels("archive is empty: no base rates for p_beat / move_ratio")
    margin = settings.probability_clip
    weights = settings.p_up_feature_map
    params: dict[ModelName, tuple[ModelParams, dict[str, float]]] = {
        "p_up": (
            ModelParams(
                intercept=0.0,
                betas={w.feature: settings.p_up_initial_betas[k] for k, w in weights.items()},
                scales={w.feature: w.scale for w in weights.values()},
            ),
            {},
        ),
        "p_beat": (
            ModelParams(intercept=logit(clip(float(beat_rate), margin))),
            {"base_rate": float(beat_rate), "n": float(beat_n)},
        ),
        "move_ratio": (
            ModelParams(intercept=logit(clip(float(move_rate), margin))),
            {"base_rate": float(move_rate), "n": float(move_n)},
        ),
    }
    for name, (model_params, metrics) in params.items():
        session.add(
            orm.ModelVersion(
                model=name,
                version=PRIOR_VERSION,
                params=model_params.model_dump(),
                metrics=metrics or None,
                trained_at=now,
                accepted=True,
                reason="стартовая версия: веса SPEC §9 и частоты архива, до первого learn season",
            )
        )
    session.flush()
    return True


def active_models(session: Session) -> ActiveModels:
    """Последняя принятая версия, у которой есть все три модели."""
    rows = session.scalars(
        select(orm.ModelVersion)
        .where(orm.ModelVersion.accepted.is_(True))
        .order_by(orm.ModelVersion.trained_at.desc(), orm.ModelVersion.id.desc())
    ).all()
    by_version: dict[str, dict[ModelName, ModelParams]] = {}
    order: list[str] = []
    for row in rows:
        if row.version not in by_version:
            by_version[row.version] = {}
            order.append(row.version)
        for name in MODEL_NAMES:
            if row.model == name:
                by_version[row.version][name] = ModelParams.model_validate(row.params)
    for version in order:
        if set(by_version[version]) == set(MODEL_NAMES):
            return ActiveModels(version, by_version[version])
    raise NoModels("no accepted model version: run `make models-init`")
