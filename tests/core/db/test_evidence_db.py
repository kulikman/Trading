from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from core.config import load_config
from core.db import models as orm
from core.db.store import sync_universe
from core.registry.promote import promote
from core.registry.state import plugin_state, sync_plugins
from learning.evidence import DbEvidence

CONFIG = load_config()
NOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)


def trades(session: Session, strategy: str, pnls: list[float], ticker: str = "NFLX") -> None:
    """Закрытые paper-сделки стратегии, риск 1% от $100 000 = $1000."""
    for i, pnl in enumerate(pnls):
        event = orm.Event(
            ticker=ticker,
            report_date=date(2026, 10, 1) + timedelta(days=i),
            report_time="AMC",
            date_status="confirmed",
        )
        session.add(event)
        session.flush()
        session.add(
            orm.DecisionStep(
                event_id=event.id,
                stage="T-1",
                job="straddle_decision",
                strategy_id=strategy,
                is_shadow=False,
                outcome="proposal",
                mode="move",
                construction="straddle",
                reasons=[],
                risk_fraction=0.01,
                at=NOW,
            )
        )
        decision = orm.Decision(
            event_id=event.id,
            status="ENTERED",
            reasons=[],
            mode="move",
            strategy_id=strategy,
            construction="straddle",
            decided_at=NOW,
        )
        session.add(decision)
        session.flush()
        session.add(
            orm.TradeCard(
                decision_id=decision.id, state="CLOSED", paper=True, legs=[], pnl_total=Decimal(pnl)
            )
        )
    session.flush()


def test_paper_strategy_promoted_to_real_by_sharpe(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    sync_plugins(session, CONFIG.registry)
    trades(session, "mode_c", [600.0, -400.0] * 15)  # 30 сделок, средняя +0,1 риска
    evidence = DbEvidence(session, CONFIG.thresholds)
    state = plugin_state(session, "mode_c", "0.1.0")
    assert state is not None
    found = evidence.evidence(state)
    assert (found.metric, found.observations, found.baseline) == ("sharpe", 30, 0.0)
    assert found.candidate is not None
    assert round(found.candidate, 4) == 0.2  # 0,1 / 0,5
    result = promote(
        session,
        "mode_c",
        "0.1.0",
        source=evidence,
        lifecycle=CONFIG.thresholds.lifecycle,
        now=NOW,
    )
    assert (result.accepted, result.to_stage) == (True, "live_small")


def test_too_few_trades_refused(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    sync_plugins(session, CONFIG.registry)
    trades(session, "mode_c", [600.0, -400.0] * 10)  # 20 сделок
    evidence = DbEvidence(session, CONFIG.thresholds)
    lifecycle = CONFIG.thresholds.lifecycle
    few = promote(session, "mode_c", "0.1.0", source=evidence, lifecycle=lifecycle, now=NOW)
    assert (few.accepted, few.reason) == (False, "мало наблюдений: 20 из 30")


def test_losing_trades_refused(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    sync_plugins(session, CONFIG.registry)
    trades(session, "mode_c", [-600.0, 400.0] * 15, "TSLA")  # 30 сделок, Sharpe < 0
    evidence = DbEvidence(session, CONFIG.thresholds)
    lifecycle = CONFIG.thresholds.lifecycle
    losing = promote(session, "mode_c", "0.1.0", source=evidence, lifecycle=lifecycle, now=NOW)
    assert not losing.accepted
    assert losing.reason.startswith("sharpe не лучше базового: -0.2000 против 0.0000")


def test_agent_brier_from_season(session: Session) -> None:
    sync_plugins(session, CONFIG.registry)
    session.add(
        orm.ModelVersion(
            model="p_up",
            version="0.2.0",
            params={"intercept": 0.0},
            metrics={"n": 40, "brier": 0.21, "contributions": {"options": 0.03}},
            trained_at=NOW,
            accepted=True,
            reason="test",
        )
    )
    session.flush()
    state = plugin_state(session, "options", "0.1.0")
    assert state is not None
    found = DbEvidence(session, CONFIG.thresholds).evidence(state)
    assert (found.metric, found.observations, found.candidate) == ("brier", 40, 0.21)
    assert found.baseline is not None
    assert round(found.baseline, 4) == 0.24  # без опционов Brier хуже
