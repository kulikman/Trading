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
        "straddle": FakeStrategy("straddle", proposal("straddle")),
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
        ("straddle", "proposal", False, []),
        ("iron_condor", "proposal", False, []),
    ]
    decisions = session.scalars(select(orm.Decision).order_by(orm.Decision.id)).all()
    assert [(d.status, d.strategy_id) for d in decisions] == [
        ("ENTERED", "straddle"),  # сбор данных: вход на каждую прошедшую paper-стратегию
        ("ENTERED", "iron_condor"),
    ]
    assert finalize(session, event.id, NOW) == list(decisions)  # входы есть — SKIPPED не нужен
    sized = session.scalars(
        select(orm.DecisionStep).where(orm.DecisionStep.strategy_id == "iron_condor")
    ).one()
    assert sized.risk_fraction == pytest.approx(0.01)  # сезоны 1–2: фиксированный риск 1%
    ctx = condor.contexts[0]
    assert ctx.forecasts["market_move"] == pytest.approx(0.36)  # 0,30 − (−0,06)
    assert ctx.features["macro"] == {"regime": 0.0}


def test_entry_opens_planned_paper_card_once(session: Session, event: orm.Event) -> None:
    strategies: dict[str, Strategy] = {
        "iron_condor": FakeStrategy("iron_condor", proposal("iron_condor"))
    }
    for _ in range(2):
        run_decision(session, job(event.id), ["iron_condor"], strategies, config=CONFIG, now=NOW)
    card = session.scalars(select(orm.TradeCard)).one()  # повтор задачи — вторая карточка не нужна
    assert (card.state, card.paper) == ("PLANNED", True)
    transition = session.scalars(select(orm.TradeCardTransition)).one()
    assert (transition.from_state, transition.to_state, transition.at) == (None, "PLANNED", NOW)


def learned_models(session: Session) -> None:
    """Две версии сверх стартовой — сезоны 1–2 закончились, ворота edge и θ действуют."""
    for version in ("0.2.0", "0.3.0"):
        session.add(
            orm.ModelVersion(
                model="p_up",
                version=version,
                params={"intercept": 0.0},
                trained_at=NOW,
                accepted=True,
                reason="test",
            )
        )
    session.flush()


def test_collecting_skips_edge_gate_but_keeps_quarantine(
    session: Session, event: orm.Event
) -> None:
    weak: dict[str, Strategy] = {
        "iron_condor": FakeStrategy("iron_condor", proposal("iron_condor", edge=0.0, p=0.4))
    }
    run_decision(session, job(event.id), ["iron_condor"], weak, config=CONFIG, now=NOW)
    assert steps(session) == [("iron_condor", "proposal", False, [])]  # широкая воронка
    step = session.scalars(select(orm.DecisionStep)).one()
    assert (step.edge, step.confidence) == (0.0, 0.4)  # записано для сужения воронки потом
    other = orm.Event(ticker="TSLA", report_date=date(2026, 10, 20), date_status="projected")
    session.add(other)
    company = session.get(orm.Company, "TSLA")
    assert company is not None
    company.calibration_status = "quarantine"
    session.flush()
    run_decision(session, job(other.id), ["iron_condor"], weak, config=CONFIG, now=NOW)
    assert steps(session)[-1] == ("iron_condor", "skip", False, ["CALIBRATION"])


def test_gates_after_learning_and_finalize_collects_reasons(
    session: Session, event: orm.Event
) -> None:
    learned_models(session)
    strategies: dict[str, Strategy] = {
        "iron_condor": FakeStrategy("iron_condor", proposal("iron_condor", edge=0.04, p=0.45)),
    }
    run_decision(session, job(event.id), ["iron_condor"], strategies, config=CONFIG, now=NOW)
    assert steps(session) == [
        ("iron_condor", "skip", False, ["EDGE_LOW", "CONF_LOW"])  # 0,04 ≤ 0,02 + 0,03; 0,45 < θ
    ]
    assert session.scalars(select(orm.Decision)).first() is None
    [decision] = finalize(session, event.id, NOW)
    assert (decision.status, sorted(decision.reasons)) == ("SKIPPED", ["CONF_LOW", "EDGE_LOW"])
    assert finalize(session, event.id, NOW) == [decision]  # повтор не создаёт второго


def test_kelly_after_learning(session: Session, event: orm.Event) -> None:
    learned_models(session)
    strategies: dict[str, Strategy] = {
        "iron_condor": FakeStrategy("iron_condor", proposal("iron_condor")),
    }
    run_decision(session, job(event.id), ["iron_condor"], strategies, config=CONFIG, now=NOW)
    step = session.scalars(select(orm.DecisionStep)).one()
    assert step.risk_fraction == pytest.approx(0.25 * (0.64 - 0.36))  # ¼ Келли после сезонов 1–2


def test_mode_c_without_model_keeps_signal_entry_after_learning(
    session: Session, event: orm.Event
) -> None:
    learned_models(session)
    signal = proposal("mode_c", edge=0.0, p=0.0, mode="C")  # у режима C нет модели
    strategies: dict[str, Strategy] = {"mode_c": FakeStrategy("mode_c", signal)}
    run_decision(session, job(event.id), ["mode_c"], strategies, config=CONFIG, now=NOW)
    step = session.scalars(select(orm.DecisionStep)).one()
    assert step.outcome == "proposal"
    assert step.risk_fraction == pytest.approx(0.01)  # фиксированный риск, без Келли


def test_finalize_without_steps_is_data_calendar(session: Session, event: orm.Event) -> None:
    assert finalize(session, event.id, NOW)[0].reasons == ["DATA_CALENDAR"]


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
