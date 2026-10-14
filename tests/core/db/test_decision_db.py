from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import load_config
from core.db import models as orm
from core.db.store import sync_universe
from core.domain.schedule import EventJob
from core.domain.trading import TradeCard
from core.registry.protocols import (
    Action,
    DecisionContext,
    MarketState,
    Proposal,
    Skip,
    Strategy,
)
from core.registry.state import sync_plugins
from decision.chief import finalize, run_decision
from decision.jobs import FINALIZE_JOBS, decision_handlers

CONFIG = load_config()
NOW = datetime(2026, 10, 19, 19, 10, tzinfo=UTC)  # T−1 15:10 ET


class FakeStrategy:
    """Подставная стратегия: отдаёт заданное предложение или отказ."""

    version = "0.1.0"
    mode = "move"

    def __init__(self, strategy_id: str, result: Proposal | Skip) -> None:
        self.id = strategy_id
        self.result = result
        self.contexts: list[DecisionContext] = []

    def evaluate(self, ctx: DecisionContext) -> Proposal | Skip:
        self.contexts.append(ctx)
        return self.result

    def exit_rules(self, card: TradeCard, market: MarketState) -> list[Action]:
        return []


def proposal(
    strategy_id: str, *, edge: float = 0.10, p: float = 0.64, cost: float = 0.02, mode: str = "move"
) -> Proposal:
    return Proposal(
        strategy_id=strategy_id,
        mode=mode,
        construction=strategy_id,
        edge=edge,
        confidence=p,
        probability=p,
        cost_fraction=cost,
    )


@pytest.fixture
def event(session: Session) -> orm.Event:
    sync_universe(session, CONFIG.universe)
    sync_plugins(session, CONFIG.registry)  # mode_a, mode_b — shadow; straddle, iron_condor — paper
    row = orm.Event(
        ticker="NFLX", report_date=date(2026, 10, 20), report_time="AMC", date_status="confirmed"
    )
    session.add(row)
    session.flush()
    session.add(
        orm.FeatureSnapshot(
            event_id=row.id,
            stage="T-1",
            agent_id="macro",
            agent_version="0.1.0",
            features={"regime": 0.0},
        )
    )
    session.add(
        orm.Forecast(
            event_id=row.id,
            stage="T-1",
            model_version="0.1.0",
            p_up=0.55,
            move_ratio=0.30,
            market_p_up=0.5,
            edge_up=0.05,
            edge_move=-0.06,
            implied_move=0.08,
        )
    )
    session.flush()
    return row


def job(event_id: int, name: str = "mode_b_decision", stage: str = "T-1") -> EventJob:
    return EventJob(event_id=event_id, stage=stage, job=name, kind="analysis", run_at=NOW)


def steps(session: Session) -> list[tuple[str, str, bool, list[str]]]:
    rows = session.scalars(select(orm.DecisionStep).order_by(orm.DecisionStep.id)).all()
    return [(r.strategy_id, r.outcome, r.is_shadow, list(r.reasons)) for r in rows]


def test_paper_proposal_enters_shadow_only_records(session: Session, event: orm.Event) -> None:
    condor = FakeStrategy("iron_condor", proposal("iron_condor"))
    strategies: dict[str, Strategy] = {
        "mode_b": FakeStrategy("mode_b", proposal("mode_b", edge=0.3, p=0.9, mode="B")),
        "iron_condor": condor,
        "straddle": FakeStrategy("straddle", Skip("straddle", ["EDGE_LOW"])),
    }
    run_decision(
        session,
        job(event.id),
        ["mode_b", "straddle", "iron_condor"],
        strategies,
        config=CONFIG,
        now=NOW,
    )
    assert steps(session) == [
        ("mode_b", "proposal", True, []),  # shadow: считается, но не входит
        ("straddle", "skip", False, ["EDGE_LOW"]),
        ("iron_condor", "proposal", False, []),
    ]
    decision = session.scalars(select(orm.Decision)).one()
    assert (decision.status, decision.strategy_id, decision.mode) == (
        "ENTERED",
        "iron_condor",
        "move",
    )
    sized = session.scalars(
        select(orm.DecisionStep).where(orm.DecisionStep.strategy_id == "iron_condor")
    ).one()
    assert sized.risk_fraction == pytest.approx(0.125 * (0.64 - 0.36))
    ctx = condor.contexts[0]
    assert ctx.forecasts["market_move"] == pytest.approx(0.36)  # 0,30 − (−0,06)
    assert ctx.features["macro"] == {"regime": 0.0}


def test_gates_and_finalize_collects_reasons(session: Session, event: orm.Event) -> None:
    event.date_status = "projected"
    company = session.get(orm.Company, "NFLX")
    assert company is not None
    company.calibration_status = "quarantine"
    session.flush()
    strategies: dict[str, Strategy] = {
        "iron_condor": FakeStrategy("iron_condor", proposal("iron_condor", edge=0.04, p=0.45)),
    }
    run_decision(session, job(event.id), ["iron_condor"], strategies, config=CONFIG, now=NOW)
    assert steps(session) == [
        (
            "iron_condor",
            "skip",
            False,
            [
                "EDGE_LOW",
                "CONF_LOW",
                "CALIBRATION",
                "DATA_MISMATCH",
            ],  # 0,04 ≤ 0,02 + 0,03; 0,45 < θ
        )
    ]
    assert session.scalars(select(orm.Decision)).first() is None
    decision = finalize(session, event.id, NOW)
    assert (decision.status, sorted(decision.reasons)) == (
        "SKIPPED",
        ["CALIBRATION", "CONF_LOW", "DATA_MISMATCH", "EDGE_LOW"],
    )
    assert finalize(session, event.id, NOW).id == decision.id  # повтор не создаёт второго


def test_finalize_without_steps_is_data_calendar(session: Session, event: orm.Event) -> None:
    assert finalize(session, event.id, NOW).reasons == ["DATA_CALENDAR"]


def test_rerun_does_not_duplicate_steps_or_decisions(session: Session, event: orm.Event) -> None:
    strategies: dict[str, Strategy] = {
        "iron_condor": FakeStrategy("iron_condor", proposal("iron_condor"))
    }
    for _ in range(2):
        run_decision(session, job(event.id), ["iron_condor"], strategies, config=CONFIG, now=NOW)
    assert len(steps(session)) == 1
    assert len(session.scalars(select(orm.Decision)).all()) == 1


def test_handlers_cover_decision_and_finalize_jobs() -> None:
    handlers = decision_handlers(CONFIG, {})
    assert {"mode_a_decision", "mode_b_gate", "mode_b_decision"} <= set(handlers)
    assert set(FINALIZE_JOBS) <= set(handlers)


def test_finalize_job_handler(session: Session, event: orm.Event) -> None:
    handlers = decision_handlers(CONFIG, {})
    handlers["outcome"](session, job(event.id, "outcome", "T+1"))
    assert session.scalars(select(orm.Decision)).one().status == "SKIPPED"
