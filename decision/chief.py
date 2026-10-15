"""Chief Trader (SPEC §10, T16): стратегии задачи → ворота → размер → шаги и Decision.

Каждая стратегия задачи даёт предложение или отказ с кодами; предложение проходит ворота:
edge > costs + 0,03 (EDGE_LOW), уверенность ≥ θ режима (CONF_LOW), компания не в карантине для
режимов, кроме C (CALIBRATION), затем Capital Manager (Келли).
Сезоны 1–2 — сбор данных (решение заказчика 15.10.2026): ворота edge и θ не применяются, риск —
фиксированный (sizing.data_collection_risk); edge и уверенность всё равно пишутся в шаг. Режимы
без модели (C) так и считаются после сезонов 1–2, пока T20 не даст им оценку.
Все шаги пишутся в decision_step; shadow-стратегии считают, но в решение не идут (SPEC §7).
Входов у события может быть несколько — ENTERED на каждую прошедшую paper-стратегию (сбор
данных, решение заказчика 15.10.2026); без входов после T0 — один SKIPPED с кодами всех отказов и
нерешённых сбоев источников по событию (DATA_FINNHUB, DATA_ALPHAVANTAGE, DATA_MASSIVE — E2e).
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
from core.risk.market import market_level_before
from core.session_guard import to_et
from decision.capital import (
    Rejection,
    Sizing,
    in_seasons_1_2,
    level_from_regime,
    size,
    size_data_collection,
    win_loss_ratio,
)
from execution.cards import open_card
from models.features import stage_features

NO_DECISION_RUN: list[SkipReason] = ["DATA_CALENDAR"]  # задачи решения не выполнялись
# Сбой источника по событию (E2e): DataError в журнале, не решённая повтором задачи.
SOURCE_CODES: dict[str, SkipReason] = {
    "finnhub": "DATA_FINNHUB",
    "alphavantage": "DATA_ALPHAVANTAGE",
    "massive": "DATA_MASSIVE",
}
NO_MODEL_MODES = ("C",)  # у режима нет модели: вход по сигналу, фиксированный риск (до оценки T20)


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
    # Уровень закрытия накануне из ежедневной задачи (E2d); нет — уровень агента «Макро» события.
    level = market_level_before(session, to_et(job.run_at).date()) or level_from_regime(
        ctx.features.get("macro", {}).get("regime")
    )
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
        collecting = seasons_1_2 or result.mode in NO_MODEL_MODES
        reasons = _gates(result, is_quarantined, config, collecting=collecting)
        outcome: Sizing | Rejection
        if reasons:
            outcome = Rejection(reasons)
        elif collecting:
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
    for item in accepted:
        decision_id = session.execute(
            insert(orm.Decision)
            .values(
                event_id=event.id,
                status="ENTERED",
                reasons=[],
                mode=item.proposal.mode,
                strategy_id=item.proposal.strategy_id,
                construction=item.proposal.construction,
                decided_at=now,
            )
            .on_conflict_do_nothing(constraint="uq_decision_event_id_strategy_id")
            .returning(orm.Decision.id)
        ).scalar_one_or_none()
        if decision_id is not None:  # новый вход — карточка paper-сделки
            decision = session.get(orm.Decision, decision_id)
            if decision is not None:
                open_card(session, decision)
    session.flush()
    return steps


def finalize(session: Session, event_id: int, now: datetime) -> list[orm.Decision]:
    """Итог события после T0: входы, а если их не было — один SKIPPED с кодами всех отказов."""
    existing = list(
        session.scalars(
            select(orm.Decision).where(orm.Decision.event_id == event_id).order_by(orm.Decision.id)
        )
    )
    if existing:
        return existing
    steps = session.scalars(
        select(orm.DecisionStep).where(
            orm.DecisionStep.event_id == event_id, orm.DecisionStep.is_shadow.is_(False)
        )
    ).all()
    found = {r for step in steps for r in step.reasons} | set(data_failures(session, event_id))
    reasons = sorted(found) or list(NO_DECISION_RUN)
    decision = orm.Decision(event_id=event_id, status="SKIPPED", reasons=reasons, decided_at=now)
    session.add(decision)
    session.flush()
    return [decision]


def data_failures(session: Session, event_id: int) -> list[SkipReason]:
    """Коды DATA_* источников, которые упали по событию и не восстановились (E2e)."""
    messages = session.scalars(
        select(orm.ErrorLog.message).where(
            orm.ErrorLog.event_id == event_id,
            orm.ErrorLog.error_type == "DataError",
            orm.ErrorLog.resolved_at.is_(None),
        )
    ).all()
    codes = {SOURCE_CODES.get(m.split(":", 1)[0].strip()) for m in messages}  # «finnhub: …»
    return sorted(c for c in codes if c is not None)


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
