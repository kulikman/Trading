"""Chief Trader (SPEC §10, T16): стратегии задачи → ворота → размер → шаги и Decision.

Каждая стратегия задачи даёт предложение или отказ с кодами; предложение проходит ворота:
edge > costs + 0,03 (EDGE_LOW), уверенность ≥ θ режима (CONF_LOW), компания не в карантине для
режимов, кроме C (CALIBRATION), затем Capital Manager (Келли).
Сезоны 1–2 — сбор данных (решение заказчика 15.10.2026): ворота edge и θ не применяются, риск —
фиксированный (sizing.data_collection_risk); edge и уверенность всё равно пишутся в шаг.
Все шаги пишутся в decision_step; shadow-стратегии считают, но в решение не идут (SPEC §7).
Decision у события один: ENTERED — при первом прошедшем предложении (лучшее по edge × риск);
иначе после T0 — SKIPPED с кодами всех отказов (`finalize`).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.config import AppConfig
from core.db import models as orm
from core.domain.earnings import DecisionStepRecord
from core.domain.schedule import EventJob
from core.domain.types import FeatureStage, SkipReason
from core.registry.agent_jobs import REPORT_TIMES, STAGES, feature_stage
from core.registry.protocols import DecisionContext, EventContext, Proposal, Skip, Strategy
from core.registry.state import influences_decision, plugin_state
from decision.capital import (
    Rejection,
    Sizing,
    in_seasons_1_2,
    level_from_regime,
    size,
    size_data_collection,
    win_loss_ratio,
)
from models.features import stage_features

NO_DECISION_RUN: list[SkipReason] = ["DATA_CALENDAR"]  # задачи решения не выполнялись


@dataclass(frozen=True)
class Accepted:
    proposal: Proposal
    sizing: Sizing


def decision_context(
    session: Session, event: orm.Event, stage: FeatureStage, config: AppConfig, as_of: datetime
) -> DecisionContext:
    """Признаки (последние на стадии ≤ текущей) и последний прогноз события."""
    grouped: dict[str, dict[str, float]] = {}
    for key, value in stage_features(session, event.id, stage, config.registry).items():
        agent, name = key.split(".", 1)
        grouped.setdefault(agent, {})[name] = value
    return DecisionContext(
        event=EventContext(
            event_id=event.id,
            ticker=event.ticker,
            report_date=event.report_date,
            report_time=REPORT_TIMES.get(event.report_time) if event.report_time else None,
            stage=stage,
            as_of=as_of,
            session=session,
        ),
        features=grouped,
        forecasts=_forecasts(session, event.id, stage),
    )


def run_decision(
    session: Session,
    job: EventJob,
    strategy_ids: Sequence[str],
    strategies: Mapping[str, Strategy],
    *,
    config: AppConfig,
    now: datetime,
) -> list[DecisionStepRecord]:
    """Решение задачи события: шаги каждой стратегии и, если есть прошедшее предложение, ENTERED."""
    event = session.get(orm.Event, job.event_id)
    if event is None:
        raise ValueError(f"event {job.event_id} not found")
    stage = feature_stage(job.stage)
    ctx = decision_context(session, event, stage, config, job.run_at)
    company = session.get(orm.Company, event.ticker)
    is_quarantined = company is not None and company.calibration_status == "quarantine"
    level = level_from_regime(ctx.features.get("macro", {}).get("regime"))
    seasons_1_2 = in_seasons_1_2(session)
    steps: list[DecisionStepRecord] = []
    accepted: list[Accepted] = []
    for strategy_id in strategy_ids:
        strategy = strategies.get(strategy_id)
        if strategy is None:
            continue  # стратегия выключена в registry.yaml
        state = plugin_state(session, strategy.id, strategy.version)
        is_shadow = state is None or not influences_decision(state.stage)
        result = strategy.evaluate(ctx)
        if isinstance(result, Skip):
            steps.append(_step(job, strategy.id, is_shadow, now, reasons=list(result.reasons)))
            continue
        reasons = _gates(result, is_quarantined, config, collecting=seasons_1_2)
        outcome: Sizing | Rejection
        if reasons:
            outcome = Rejection(reasons)
        elif seasons_1_2:
            outcome = size_data_collection(result, level=level, thresholds=config.thresholds)
        else:
            outcome = size(
                result,
                level=level,
                b=win_loss_ratio(session, result.construction, config.thresholds),
                seasons_1_2=seasons_1_2,
                thresholds=config.thresholds,
            )
        steps.append(_step(job, strategy.id, is_shadow, now, result, outcome))
        if isinstance(outcome, Sizing) and not is_shadow:
            accepted.append(Accepted(result, outcome))
    for record in steps:
        session.execute(
            insert(orm.DecisionStep)
            .values(record.model_dump(exclude={"id"}))
            .on_conflict_do_nothing(index_elements=["event_id", "stage", "job", "strategy_id"])
        )
    if (
        accepted
        and session.scalars(select(orm.Decision).where(orm.Decision.event_id == event.id)).first()
        is None
    ):
        best = max(accepted, key=lambda a: a.proposal.edge * a.sizing.risk_fraction)
        session.add(
            orm.Decision(
                event_id=event.id,
                status="ENTERED",
                reasons=[],
                mode=best.proposal.mode,
                strategy_id=best.proposal.strategy_id,
                construction=best.proposal.construction,
                decided_at=now,
            )
        )
    session.flush()
    return steps


def finalize(session: Session, event_id: int, now: datetime) -> orm.Decision:
    """Итог события после T0: если входа не было — SKIPPED с кодами всех отказов."""
    existing = session.scalars(
        select(orm.Decision).where(orm.Decision.event_id == event_id)
    ).first()
    if existing is not None:
        return existing
    steps = session.scalars(
        select(orm.DecisionStep).where(
            orm.DecisionStep.event_id == event_id, orm.DecisionStep.is_shadow.is_(False)
        )
    ).all()
    reasons = sorted({r for step in steps for r in step.reasons}) or list(NO_DECISION_RUN)
    decision = orm.Decision(event_id=event_id, status="SKIPPED", reasons=reasons, decided_at=now)
    session.add(decision)
    session.flush()
    return decision


def _gates(
    proposal: Proposal, is_quarantined: bool, config: AppConfig, *, collecting: bool
) -> list[SkipReason]:
    thresholds = config.thresholds
    reasons: list[SkipReason] = []
    if is_quarantined and proposal.mode != "C":
        reasons.append("CALIBRATION")  # в карантине разрешён только режим C (SPEC §9)
    if collecting:
        return reasons  # сезоны 1–2: широкая воронка, edge и θ только записываются
    theta = (
        thresholds.modes.B.theta
        if proposal.mode == "B"
        else thresholds.edge.paper_theta_seasons_1_2
    )
    if proposal.edge <= proposal.cost_fraction + thresholds.edge.margin_over_costs:
        reasons.append("EDGE_LOW")
    if proposal.confidence < theta:
        reasons.append("CONF_LOW")
    return reasons


def _step(
    job: EventJob,
    strategy_id: str,
    is_shadow: bool,
    now: datetime,
    proposal: Proposal | None = None,
    outcome: Sizing | Rejection | None = None,
    reasons: list[SkipReason] | None = None,
) -> DecisionStepRecord:
    if proposal is None:
        return DecisionStepRecord(
            event_id=job.event_id,
            stage=job.stage,
            job=job.job,
            strategy_id=strategy_id,
            is_shadow=is_shadow,
            outcome="skip",
            reasons=reasons or [],
            at=now,
        )
    is_sized = isinstance(outcome, Sizing)
    return DecisionStepRecord(
        event_id=job.event_id,
        stage=job.stage,
        job=job.job,
        strategy_id=strategy_id,
        is_shadow=is_shadow,
        outcome="proposal" if is_sized else "skip",
        mode=proposal.mode,
        construction=proposal.construction,
        reasons=list(outcome.reasons) if isinstance(outcome, Rejection) else [],
        edge=proposal.edge,
        confidence=proposal.confidence,
        probability=proposal.probability,
        cost_fraction=proposal.cost_fraction,
        risk_fraction=outcome.risk_fraction if isinstance(outcome, Sizing) else None,
        at=now,
    )


def _forecasts(session: Session, event_id: int, stage: FeatureStage) -> dict[str, float]:
    """Последний прогноз события на стадии не позже текущей (поля без None)."""
    allowed = STAGES[: STAGES.index(stage) + 1]
    rows = session.scalars(
        select(orm.Forecast)
        .where(orm.Forecast.event_id == event_id, orm.Forecast.stage.in_(allowed))
        .order_by(orm.Forecast.created_at.desc())
    ).all()
    if not rows:
        return {}
    latest = max(rows, key=lambda r: (allowed.index(r.stage), r.created_at))
    values = {
        "p_beat": latest.p_beat,
        "p_up": latest.p_up,
        "move_ratio": latest.move_ratio,
        "market_p_beat": latest.market_p_beat,
        "market_p_up": latest.market_p_up,
        "edge_up": latest.edge_up,
        "edge_move": latest.edge_move,
        "implied_move": latest.implied_move,
    }
    if latest.move_ratio is not None and latest.edge_move is not None:
        values["market_move"] = latest.move_ratio - latest.edge_move
    return {k: float(v) for k, v in values.items() if v is not None}
