from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from adapters.finnhub.models import FinnhubEarning
from agents.consensus.snapshot import take_consensus_snapshot
from core.db import models as orm
from core.db.store import save_consensus_snapshots, save_news
from core.domain.earnings import ConsensusSnapshot
from core.domain.news import NewsItem
from tests.adapters.fakes import load_json

DAY = date(2026, 10, 13)
TICKERS = ("GS", "MS", "NFLX", "TSLA")


def seed_companies(session: Session) -> None:
    session.add(orm.Sector(id="mixed", name="Mixed", key_metrics=["x"]))
    session.flush()
    session.add_all(orm.Company(ticker=t, sector_id="mixed", name=t) for t in TICKERS)
    session.flush()


def snapshot_rows(session: Session) -> list[tuple[str, str, date, float | None]]:
    rows = session.execute(
        select(
            orm.ConsensusSnapshot.ticker,
            orm.ConsensusSnapshot.fiscal_period,
            orm.ConsensusSnapshot.as_of,
            orm.ConsensusSnapshot.eps_estimate,
        ).order_by(orm.ConsensusSnapshot.ticker, orm.ConsensusSnapshot.as_of)
    ).all()
    return [tuple(r) for r in rows]  # type: ignore[misc]


def test_repeat_snapshot_same_day_updates_instead_of_duplicating(session: Session) -> None:
    seed_companies(session)
    snap = ConsensusSnapshot(ticker="GS", fiscal_period="2026Q3", as_of=DAY, eps_estimate=11.8)
    save_consensus_snapshots(session, [snap])
    save_consensus_snapshots(session, [snap.model_copy(update={"eps_estimate": 11.9})])
    assert snapshot_rows(session) == [("GS", "2026Q3", DAY, 11.9)]


def test_next_day_snapshot_is_a_new_row(session: Session) -> None:
    seed_companies(session)
    snap = ConsensusSnapshot(ticker="GS", fiscal_period="2026Q3", as_of=DAY, eps_estimate=11.8)
    save_consensus_snapshots(
        session, [snap, snap.model_copy(update={"as_of": DAY + timedelta(days=1)})]
    )
    assert len(snapshot_rows(session)) == 2


def test_empty_batches_are_noops(session: Session) -> None:
    assert save_consensus_snapshots(session, []) == 0
    assert save_news(session, []) == 0


class CalendarFixture:
    def __init__(self) -> None:
        self.calls: list[tuple[date, date]] = []

    def earnings_calendar(
        self, start: date, end: date, symbol: str | None = None
    ) -> list[FinnhubEarning]:
        self.calls.append((start, end))
        rows = load_json("finnhub", "earnings_calendar.json")["earningsCalendar"]
        return [FinnhubEarning.model_validate(r) for r in rows]


def test_daily_consensus_snapshot_job_is_idempotent(session: Session) -> None:
    seed_companies(session)
    source = CalendarFixture()
    for _ in range(2):
        saved = take_consensus_snapshot(
            source, session, as_of=DAY, lookahead_days=30, tickers=TICKERS
        )
        assert saved == 3  # MS, NFLX, TSLA; BAC, ADC, ADX — вне вселенной теста
    assert source.calls[0] == (DAY, DAY + timedelta(days=30))
    assert [r[0] for r in snapshot_rows(session)] == ["MS", "NFLX", "TSLA"]


def test_news_saved_once_and_existing_tags_kept(session: Session) -> None:
    item = NewsItem(
        id="massive:1",
        source="massive",
        published_at=datetime(2026, 10, 13, 12, tzinfo=UTC),
        title="t",
        url="https://example.com",
        tickers=["GS"],
        tags=["management"],
    )
    assert save_news(session, [item]) == 1
    assert save_news(session, [item.model_copy(update={"tags": None, "title": "changed"})]) == 0
    count = session.execute(select(func.count()).select_from(orm.NewsArticle)).scalar_one()
    stored = session.get(orm.NewsArticle, "massive:1")
    assert count == 1
    assert stored is not None
    assert (stored.title, stored.tags) == ("t", ["management"])


def test_financial_quarter_restatement_updates_row(session: Session) -> None:
    from core.db.store import save_financial_quarters
    from core.domain.financials import FinancialQuarter

    seed_companies(session)
    q = FinancialQuarter(
        ticker="GS",
        metric="net_income",
        period_start=date(2026, 4, 1),
        period_end=date(2026, 6, 30),
        value=6_628_000_000,
        unit="USD",
        derived=False,
        concept="NetIncomeLoss",
        form="10-Q",
        accession="a1",
        filed=date(2026, 8, 3),
    )
    assert save_financial_quarters(session, [q]) == 1
    save_financial_quarters(
        session, [q.model_copy(update={"value": 6_700_000_000, "accession": "a2"})]
    )
    rows = session.execute(select(orm.FinancialQuarter)).scalars().all()
    assert [(r.value, r.accession) for r in rows] == [(6_700_000_000, "a2")]
    assert save_financial_quarters(session, []) == 0
