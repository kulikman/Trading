"""Capital Manager и Black Swan (SPEC §10): размер риска сделки и вето по уровню рынка.

Риск на сделку (доля капитала) = множитель Келли · (p·b − (1−p)) / b; в сезоны 1–2 — ⅛ вместо ¼.
b = W/L по истории конструкции, пока у неё меньше правила 30 закрытых сделок — kelly_initial_b.
Black Swan: жёлтый — размер × 0,7; оранжевый — только уверенность > 0,8 и размер × 0,4;
красный (или ручной красный от заказчика) — новых входов нет (MACRO_BLOCK).
Лимиты кластера и сезона отключены решением заказчика 2026-10-13 (null в thresholds.yaml).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.config.thresholds import Thresholds
from core.db import models as orm
from core.domain.types import SkipReason
from core.registry.protocols import Proposal
from core.risk.black_swan import ORDER, Level
from models.versions import PRIOR_VERSION

CLOSED_STATES = ("CLOSED", "STOPPED")


@dataclass(frozen=True)
class Sizing:
    risk_fraction: float  # доля капитала под риском
    level: Level


@dataclass(frozen=True)
class Rejection:
    reasons: Sequence[SkipReason]


def size(
    proposal: Proposal,
    *,
    level: Level,
    b: float,
    seasons_1_2: bool,
    thresholds: Thresholds,
) -> Sizing | Rejection:
    """Риск сделки после Келли, Black Swan и правил стратегии; не прошло — коды пропуска."""
    swan = thresholds.risk_limits.black_swan
    if level == "red" or swan.manual_red:
        return Rejection(["MACRO_BLOCK"])
    settings = {"yellow": swan.yellow, "orange": swan.orange}.get(level)
    minimum = None if settings is None else settings.min_confidence
    if minimum is not None and proposal.confidence <= minimum:
        return Rejection(["MACRO_BLOCK"])
    sizing = thresholds.sizing
    multiplier = sizing.kelly_multiplier_seasons_1_2 if seasons_1_2 else sizing.kelly_multiplier
    p = proposal.probability
    kelly = multiplier * (p * b - (1 - p)) / b
    if kelly <= 0:
        return Rejection(["EDGE_LOW"])  # при p·b ≤ 1−p риск 0 — сделки нет
    level_multiplier = settings.size_multiplier if settings is not None else 1.0
    risk = kelly * level_multiplier * proposal.size_multiplier
    if sizing.max_risk_per_trade is not None:
        risk = min(risk, sizing.max_risk_per_trade)
    return Sizing(risk_fraction=risk, level=level)


def size_real(
    proposal: Proposal,
    *,
    level: Level,
    b: float,
    seasons_1_2: bool,
    weight: float,
    first_days: bool,
    no_model: bool,
    thresholds: Thresholds,
) -> Sizing | Rejection:
    """Риск Real-сделки (E10, решение заказчика 15.10.2026 — по SPEC).

    Модель есть — Келли (`size`: ¼, в сезоны 1–2 ⅛) с вето и множителями Black Swan; режим без
    модели — фиксированный риск сбора данных × множитель уровня (красный — вето). Затем × вес стадии
    (live_small — 5%, SPEC §7) и × 0,5 в первые 30 дней Real (SPEC §14, фаза 4).
    """
    swan = thresholds.risk_limits.black_swan
    if no_model:
        if level == "red" or swan.manual_red:
            return Rejection(["MACRO_BLOCK"])
        settings = {"yellow": swan.yellow, "orange": swan.orange}.get(level)
        multiplier = settings.size_multiplier if settings is not None else 1.0
        base: Sizing | Rejection = Sizing(
            risk_fraction=thresholds.sizing.data_collection_risk
            * multiplier
            * proposal.size_multiplier,
            level=level,
        )
    else:
        base = size(proposal, level=level, b=b, seasons_1_2=seasons_1_2, thresholds=thresholds)
    if isinstance(base, Rejection):
        return base
    first = thresholds.sizing.real_first_days_multiplier if first_days else 1.0
    return Sizing(risk_fraction=base.risk_fraction * weight * first, level=level)


def size_data_collection(
    proposal: Proposal, *, level: Level, thresholds: Thresholds
) -> Sizing | Rejection:
    """Сезоны 1–2, сбор данных (решения заказчика 15.10.2026): фиксированный риск по сигналу.

    Без порога edge и Келли. Black Swan в paper не режет и не уменьшает вход — нужны данные и
    по красным дням; уровень остаётся в признаке macro.regime события. Вето — только ручной
    красный уровень заказчика.
    """
    if thresholds.risk_limits.black_swan.manual_red:
        return Rejection(["MACRO_BLOCK"])
    risk = thresholds.sizing.data_collection_risk * proposal.size_multiplier
    return Sizing(risk_fraction=risk, level=level)


def level_from_regime(regime: float | None) -> Level:
    """Уровень Black Swan из признака macro.regime (0–3); признака нет — зелёный.

    Нет данных макро — не повод запрещать сделку: вето — только по фактическому сигналу.
    """
    if regime is None:
        return "green"
    index = max(0, min(len(ORDER) - 1, round(regime)))
    return ORDER[index]


def win_loss_ratio(session: Session, construction: str, thresholds: Thresholds) -> float:
    """b = средний выигрыш / средний убыток закрытых сделок конструкции (правило 30)."""
    rows = session.execute(
        select(orm.TradeCard.pnl_total)
        .join(orm.Decision, orm.Decision.id == orm.TradeCard.decision_id)
        .where(
            orm.Decision.construction == construction,
            orm.TradeCard.state.in_(CLOSED_STATES),
            orm.TradeCard.pnl_total.is_not(None),
        )
    ).scalars()
    pnl = [float(v) for v in rows if v is not None]
    wins = [v for v in pnl if v > 0]
    losses = [-v for v in pnl if v < 0]
    if len(pnl) < thresholds.models.min_segment_obs or not wins or not losses:
        return thresholds.sizing.kelly_initial_b
    return (sum(wins) / len(wins)) / (sum(losses) / len(losses))


def in_seasons_1_2(session: Session) -> bool:
    """Сезоны 1–2: пока `learn season` (T20) не принял две версии моделей сверх стартовой."""
    learned = session.scalar(
        select(func.count(func.distinct(orm.ModelVersion.version))).where(
            orm.ModelVersion.accepted.is_(True), orm.ModelVersion.version != PRIOR_VERSION
        )
    )
    return (learned or 0) < 2
