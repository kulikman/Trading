from collections.abc import Sequence
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from adapters.errors import DataError
from adapters.massive.models import Bar, TickerChange
from agents.sector.agent import SectorAgentPlugin
from core.config import load_config
from core.db import models as orm
from core.db.store import save_reported_earnings, set_date_check, sync_universe
from core.domain.earnings import ReportedEarnings
from core.domain.schedule import EventJob
from core.registry.agent_jobs import agent_handlers, features_of, run_agent
from core.registry.protocols import EventContext, Trigger
from core.session_guard import ET, previous_trading_day

CONFIG = load_config()
RUN_AT = datetime(2026, 10, 14, 11, 0, tzinfo=UTC)  # 07:00 ET
DAY = date(2026, 10, 14)


class Stocks:
    """У всех компаний одинаковый рост: 100 → 110 за 30+ дней."""

    def aggregates(self, ticker: str, *args: Any, **kwargs: Any) -> list[Bar]:
        out, day = [], DAY
        for i in range(45):
            day = previous_trading_day(day)
            close = 110.0 - i * (10.0 / 44)
            start = datetime.combine(day, time(0), tzinfo=ET).timestamp() * 1000
            out.append(
                Bar.model_validate(
                    {"o": close, "h": close, "l": close, "c": close, "v": 1, "t": start}
                )
            )
        return list(reversed(out))

    def ticker_changes(self, ticker: str) -> list[TickerChange]:
        return []


@pytest.fixture
def banks(session: Session) -> Session:
    sync_universe(session, CONFIG.universe)
    reports = [
        ("JPM", date(2026, 10, 13), 10.0),
        ("BAC", date(2026, 10, 10), 5.0),
        ("WFC", date(2026, 10, 9), -1.0),
        ("C", date(2026, 10, 9), 50.0),  # дата под сомнением — исключается
        ("MS", date(2026, 7, 15), 30.0),  # старше сезона (45 дней)
    ]
    save_reported_earnings(
        session,
        [
            ReportedEarnings(
                ticker=t,
                report_date=d,
                report_time="BMO",
                fiscal_period_end=d - timedelta(days=13),
                eps_surprise_pct=s,
            )
            for t, d, s in reports
        ],
    )
    set_date_check(session, "C", date(2026, 10, 9), None, "mismatch")
    return session


def gs_context(session: Session) -> EventContext:
    return EventContext(
        event_id=1,
        ticker="GS",
        report_date=date(2026, 10, 15),
        report_time="BMO",
        stage="T-14",
        as_of=RUN_AT,
        session=session,
    )


def test_sector_trend_by_hand_and_summary_saved_once(banks: Session) -> None:
    agent = SectorAgentPlugin(Stocks(), CONFIG.universe, CONFIG.thresholds.agents.sector)
    features = agent.run(gs_context(banks))
    assert features.peers_reported == 3
    assert features.peer_surprise_mean == pytest.approx((0.10 + 0.05 - 0.01) / 3)  # 4,67% > 2%
    assert features.trend == 1
    assert features.confidence == pytest.approx(2 / 3)  # WFC против
    assert features.sector_momentum_30d is not None
    assert features.sector_momentum_30d > 0
    agent.run(gs_context(banks))  # повтор за тот же день
    rows = banks.scalars(
        select(orm.SectorSummary).where(orm.SectorSummary.sector_id == "banks")
    ).all()
    assert len(rows) == 1
    assert (rows[0].trend, rows[0].as_of) == (1, DAY)


def test_sector_without_enough_peers_has_no_trend(banks: Session) -> None:
    small = CONFIG.thresholds.agents.sector.model_copy(update={"min_peers": 4})
    features = SectorAgentPlugin(Stocks(), CONFIG.universe, small).run(gs_context(banks))
    assert (features.trend, features.confidence) == (0, None)


def test_sector_needs_archive_session() -> None:
    agent = SectorAgentPlugin(Stocks(), CONFIG.universe, CONFIG.thresholds.agents.sector)
    ctx = EventContext(
        event_id=1, ticker="GS", report_date=DAY, report_time=None, stage="T-3", as_of=RUN_AT
    )
    with pytest.raises(DataError, match="archive session"):
        agent.run(ctx)


class Out(BaseModel):
    score: float | None = None
    flag: bool = True
    count: int = 2
    note: str = "текст для человека"


class FakeAgent:
    id = "positioning"
    version = "0.1.0"
    triggers: Sequence[Trigger] = ()
    reads: Sequence[str] = ()
    output_schema: type[BaseModel] = Out

    def __init__(self) -> None:
        self.contexts: list[EventContext] = []

    def run(self, ctx: EventContext) -> Out:
        self.contexts.append(ctx)
        return Out(score=0.5)


def test_features_are_numbers_only() -> None:
    assert features_of(Out(score=None)) == {"count": 2.0}
    assert features_of(Out(score=1.5)) == {"score": 1.5, "count": 2.0}


def test_agent_job_writes_snapshot_once(banks: Session) -> None:
    event = orm.Event(
        ticker="NFLX", report_date=date(2026, 10, 21), report_time="AMC", date_status="projected"
    )
    banks.add(event)
    banks.flush()
    job = EventJob(
        event_id=event.id, stage="T-7", job="positioning", kind="analysis", run_at=RUN_AT
    )
    agent = FakeAgent()
    handlers = agent_handlers(CONFIG.schedule, {"positioning": agent})
    assert set(handlers) == {
        "positioning"
    }  # задача с агентом, которого нет в загруженных, — без обработчика
    handlers["positioning"](banks, job)
    run_agent(banks, agent, job)  # повтор — не перезаписывает
    rows = banks.scalars(select(orm.FeatureSnapshot)).all()
    assert [(r.agent_id, r.stage, r.features) for r in rows] == [
        ("positioning", "T-7", {"score": 0.5, "count": 2.0})
    ]
    ctx = agent.contexts[0]
    assert (ctx.ticker, ctx.report_time, ctx.stage, ctx.session is banks) == (
        "NFLX",
        "AMC",
        "T-7",
        True,
    )
    assert banks.execute(select(func.count()).select_from(orm.FeatureSnapshot)).scalar_one() == 1
