from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.massive.models import Bar, TickerChange
from core.config import load_config
from core.db import models as orm
from core.db.store import save_reported_earnings, sync_universe, update_earnings
from core.domain.earnings import ReportedEarnings
from core.session_guard import ET
from execution.costs import BrokerCostModel
from learning.shadow import ShadowCalculator, shadow_candidates

CONFIG = load_config()
REPORT = date(2026, 10, 20)  # вторник BMO
TODAY = date(2026, 10, 22)
AT = datetime(2026, 10, 19, 19, 10, tzinfo=UTC)


class Stocks:
    """Закрытия 100 (ATR 2) до T−7 13.10; дальше — 103."""

    def aggregates(
        self, ticker: str, multiplier: int, timespan: str, *a: Any, **k: Any
    ) -> list[Bar]:
        out = []
        for i in range(70):
            day = date(2026, 8, 20) + timedelta(days=i)
            if day.weekday() >= 5:
                continue
            close = 100.0 if day <= date(2026, 10, 13) else 103.0
            start = datetime.combine(day, time(0), tzinfo=ET).timestamp() * 1000
            out.append(
                Bar.model_validate(
                    {"o": close, "h": close + 1, "l": close - 1, "c": close, "v": 1, "t": start}
                )
            )
        return out

    def ticker_changes(self, ticker: str) -> list[TickerChange]:
        return []


@pytest.fixture
def event(session: Session) -> orm.Event:
    sync_universe(session, CONFIG.universe)
    row = orm.Event(ticker="NFLX", report_date=REPORT, report_time="BMO", date_status="confirmed")
    session.add(row)
    session.flush()
    for stage, job, day in (
        ("T-7", "mode_a_decision", date(2026, 10, 13)),
        ("T-1", "mode_a_exit", date(2026, 10, 19)),
    ):
        session.add(
            orm.EventJob(
                event_id=row.id,
                stage=stage,
                job=job,
                kind="analysis",
                run_at=datetime.combine(day, time(15, 15), tzinfo=ET),
            )
        )
    save_reported_earnings(
        session,
        [
            ReportedEarnings(
                ticker="NFLX",
                report_date=REPORT,
                report_time="BMO",
                fiscal_period_end=date(2026, 9, 30),
            )
        ],
    )
    update_earnings(session, "NFLX", REPORT, {"actual_move": -0.05})
    session.flush()
    return row


def step(
    session: Session,
    event: orm.Event,
    strategy: str,
    construction: str,
    mode: str,
    *,
    is_shadow: bool = True,
    outcome: str = "proposal",
    p: float = 0.7,
    edge: float = 0.1,
) -> orm.DecisionStep:
    row = orm.DecisionStep(
        event_id=event.id,
        stage="T-1",
        job=f"{strategy}_job",
        strategy_id=strategy,
        is_shadow=is_shadow,
        outcome=outcome,
        mode=mode,
        construction=construction,
        edge=edge,
        confidence=p,
        probability=p,
        at=AT,
    )
    session.add(row)
    session.flush()
    return row


def calculator() -> ShadowCalculator:
    return ShadowCalculator(
        stocks=Stocks(),
        thresholds=CONFIG.thresholds,
        history=CONFIG.sources.massive.history,
        costs=BrokerCostModel(CONFIG.broker.costs["manual"]),
    )


def shadows(session: Session) -> dict[str, orm.ShadowTrade]:
    return {r.strategy_id: r for r in session.scalars(select(orm.ShadowTrade))}


def test_candidates_skip_entries_and_keep_latest(session: Session, event: orm.Event) -> None:
    step(session, event, "mode_b", "stock_collar", "B")
    latest = orm.DecisionStep(
        event_id=event.id,
        stage="T-1",
        job="later",
        strategy_id="mode_b",
        is_shadow=True,
        outcome="proposal",
        mode="B",
        construction="put_spread",
        probability=0.6,
        at=AT,
    )
    session.add(latest)
    step(session, event, "straddle", "straddle", "move", is_shadow=False)
    session.add(
        orm.Decision(
            event_id=event.id,
            status="ENTERED",
            strategy_id="straddle",
            construction="straddle",
            mode="move",
            decided_at=AT,
        )
    )
    session.flush()
    assert [(s.strategy_id, s.construction) for s in shadow_candidates(session)] == [
        ("mode_b", "put_spread")
    ]


def test_mode_b_brier_and_mode_a_pnl(session: Session, event: orm.Event) -> None:
    step(session, event, "mode_b", "put_spread", "B", p=0.7)  # медвежий, движение −5% — угадал
    step(session, event, "mode_a", "stock", "A")
    result = calculator().run(session, TODAY, retry_since=date(2026, 10, 15))
    assert result.counts == {"scored": 1, "closed": 1}
    rows = shadows(session)
    assert (rows["mode_b"].status, rows["mode_b"].pnl) == ("scored", None)
    assert rows["mode_b"].brier == pytest.approx(0.09)  # (0,7 − 1)²
    a = rows["mode_a"]
    assert (a.status, a.exit_reason, a.entry_on) == ("closed", "time", date(2026, 10, 13))
    # +3 на акцию при стопе 3 → около +1R минус издержки; pnl — при риске 1% от 100 000
    assert a.return_on_risk is not None
    assert 0.95 < a.return_on_risk < 1.0
    assert a.pnl == pytest.approx(a.return_on_risk * 1000)
    assert (
        calculator().run(session, TODAY, retry_since=date(2026, 10, 15)).counts == {}
    )  # итог не пересчитывается


def test_no_data_retried_only_inside_window(session: Session, event: orm.Event) -> None:
    step(session, event, "straddle", "straddle", "move", is_shadow=False, outcome="skip")
    assert calculator().run(session, TODAY, date(2026, 10, 15)).counts == {"no_data": 1}
    assert shadows(session)["straddle"].note == "no_implied_move"
    assert calculator().run(session, TODAY, date(2026, 10, 15)).counts == {"no_data": 1}  # повтор
    assert calculator().run(session, TODAY, date(2026, 10, 21)).counts == {}  # реакция старше окна
    assert calculator().run(session, REPORT, date(2026, 10, 1)).counts == {}  # реакция не закрылась


def test_skipped_decision_gets_best_rejected_shadow(session: Session, event: orm.Event) -> None:
    step(session, event, "mode_a", "stock", "A", is_shadow=False, outcome="skip", edge=0.2)
    step(session, event, "mode_b", "put_spread", "B", is_shadow=True)  # shadow-стадия — не в итог
    decision = orm.Decision(
        event_id=event.id, status="SKIPPED", reasons=["MACRO_BLOCK"], decided_at=AT
    )
    session.add(decision)
    session.flush()
    calculator().run(session, TODAY, date(2026, 10, 15))
    pnl = shadows(session)["mode_a"].pnl
    assert decision.shadow == {"strategy_id": "mode_a", "construction": "stock", "pnl": pnl}
    track = session.scalars(select(orm.EarningsTrack)).one()
    assert pnl is not None
    assert float(track.shadow_pnl or 0) == pytest.approx(pnl, abs=1e-3)
