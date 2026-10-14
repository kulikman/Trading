from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.db import models as orm
from core.domain.base import DomainModel
from core.domain.earnings import (
    ConsensusSnapshot,
    EarningsTrack,
    Event,
    FeatureSnapshot,
    Forecast,
    ReportAudit,
)
from core.domain.financials import FinancialQuarter
from core.domain.market import Company, PeerEdge, Sector, SectorSummary
from core.domain.news import NewsItem
from core.domain.plugin import Plugin
from core.domain.trading import Decision, TradeCard, TradeCardTransition

EXPECTED_TABLES = {
    "sector",
    "sector_summary",
    "peer_edge",
    "company",
    "report_audit",
    "earnings_track",
    "consensus_snapshot",
    "event",
    "feature_snapshot",
    "forecast",
    "decision",
    "trade_card",
    "trade_card_transition",
    "plugin",
    "news_article",
    "financial_quarter",
}
AT = datetime(2026, 10, 12, 19, 30, tzinfo=UTC)
REPORT_DAY = date(2026, 10, 14)
TWO_SOURCES = [{"source": "benzinga"}, {"source": "8-K"}]


def _tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def _save(session: Session, orm_cls: type[orm.Base], obj: DomainModel) -> Any:
    row = orm_cls(**obj.model_dump(exclude_none=True))
    session.add(row)
    session.flush()
    return row


# --- миграция ---


def test_migration_creates_all_tables(engine: Engine) -> None:
    assert _tables(engine) == EXPECTED_TABLES | {"alembic_version"}


def test_models_and_migration_do_not_drift(engine: Engine) -> None:
    with engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, orm.Base.metadata) == []


def test_every_timestamp_has_time_zone(engine: Engine) -> None:
    query = text(
        "SELECT table_name || '.' || column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND data_type = 'timestamp without time zone'"
    )
    with engine.connect() as connection:
        assert connection.execute(query).scalars().all() == []


def test_downgrade_and_upgrade_again(engine: Engine, alembic_config: Config) -> None:
    command.downgrade(alembic_config, "base")
    assert _tables(engine) == {"alembic_version"}
    command.upgrade(alembic_config, "head")
    assert _tables(engine) == EXPECTED_TABLES | {"alembic_version"}


# --- вставка и чтение каждой сущности ---


@pytest.fixture
def ctx(session: Session) -> dict[str, int]:
    """Минимальный граф: сектор → компании → событие → решение → карточка."""
    _save(session, orm.Sector, Sector(id="banks", name="Банки", key_metrics=["NII"]))
    for ticker in ("GS", "MS"):
        _save(session, orm.Company, Company(ticker=ticker, sector_id="banks", name=ticker))
    event = _save(
        session,
        orm.Event,
        Event(
            ticker="GS", report_date=REPORT_DAY, date_status="confirmed", date_sources=TWO_SOURCES
        ),
    )
    decision = _save(
        session,
        orm.Decision,
        Decision(
            event_id=event.id,
            status="ENTERED",
            mode="B",
            strategy_id="mode_b",
            construction="stock_collar",
            decided_at=AT,
        ),
    )
    card = _save(
        session,
        orm.TradeCard,
        TradeCard(decision_id=decision.id, state="PLANNED", legs=[{"symbol": "GS"}]),
    )
    return {"event": event.id, "decision": decision.id, "card": card.id}


Builder = Callable[[Session, dict[str, int]], tuple[type[orm.Base], DomainModel]]


def _decision_on_new_event(
    session: Session, ctx: dict[str, int]
) -> tuple[type[orm.Base], DomainModel]:
    event = _save(
        session, orm.Event, Event(ticker="MS", report_date=REPORT_DAY, date_status="projected")
    )
    return orm.Decision, Decision(
        event_id=event.id,
        status="SKIPPED",
        reasons=["PRE_RUN", "IV_EXPENSIVE"],
        shadow={"construction": "stock_collar", "pnl": -41.5},
        decided_at=AT,
    )


CASES: dict[str, Builder] = {
    "sector": lambda s, c: (
        orm.Sector,
        Sector(
            id="semis",
            name="Полупроводники",
            key_metrics=["data center revenue"],
            macro_sensitivity=["vix"],
            data_sources={"ir": "investor relations"},
        ),
    ),
    "company": lambda s, c: (
        orm.Company,
        Company(
            ticker="JPM",
            sector_id="banks",
            name="JPMorgan Chase",
            overview="Bank",
            segments=["CIB", "CCB"],
            risks=["credit"],
            options_liquid=True,
        ),
    ),
    "sector_summary": lambda s, c: (
        orm.SectorSummary,
        SectorSummary(
            sector_id="banks",
            as_of=REPORT_DAY,
            trend=1,
            confidence=0.7,
            peer_surprise_mean=0.04,
            sector_momentum_30d=0.02,
            facts=["fact"],
            risks=["risk"],
            text_summary="Коротко",
        ),
    ),
    "peer_edge": lambda s, c: (
        orm.PeerEdge,
        PeerEdge(from_ticker="GS", to_ticker="MS", strength=0.4, lag_days=1),
    ),
    "report_audit": lambda s, c: (
        orm.ReportAudit,
        ReportAudit(
            ticker="GS",
            fiscal_period="2026Q3",
            report_date=REPORT_DAY,
            guidance={"eps": "raised"},
            management_tone=0.3,
            summary="Итог",
            source_urls=["https://www.sec.gov/"],
        ),
    ),
    "earnings_track": lambda s, c: (
        orm.EarningsTrack,
        EarningsTrack(
            ticker="GS",
            report_date=REPORT_DAY,
            report_time="BMO",
            eps_consensus=10.5,
            eps_actual=11.2,
            guidance_change=1,
            implied_move=0.041,
            actual_move=0.058,
            move_ratio=1.41,
            reaction_cause="FICC beat",
            decision="SKIPPED",
            skip_reasons=["PRE_RUN"],
            shadow_pnl=Decimal("-123.45"),
        ),
    ),
    "consensus_snapshot": lambda s, c: (
        orm.ConsensusSnapshot,
        ConsensusSnapshot(
            ticker="GS",
            fiscal_period="2026Q3",
            as_of=REPORT_DAY,
            eps_estimate=10.5,
            rev_estimate=13.1e9,
        ),
    ),
    "event": lambda s, c: (
        orm.Event,
        Event(
            ticker="MS",
            report_date=REPORT_DAY,
            report_time="BMO",
            date_status="confirmed",
            date_sources=TWO_SOURCES,
            queue_status="profiling",
        ),
    ),
    "feature_snapshot": lambda s, c: (
        orm.FeatureSnapshot,
        FeatureSnapshot(
            event_id=c["event"],
            stage="T-7",
            agent_id="macro",
            agent_version="0.1.0",
            features={"vix": 17.2, "us10y": 4.1},
        ),
    ),
    "forecast": lambda s, c: (
        orm.Forecast,
        Forecast(
            event_id=c["event"],
            stage="T-3",
            model_version="0.1.0",
            p_beat=0.7,
            p_up=0.62,
            move_ratio=0.4,
            market_p_up=0.5,
            implied_move=0.041,
            edge_up=0.12,
            exploration=True,
        ),
    ),
    "decision": _decision_on_new_event,
    "trade_card": lambda s, c: (
        orm.TradeCard,
        TradeCard(
            decision_id=c["decision"],
            state="ARMED",
            paper=True,
            legs=[{"side": "buy", "symbol": "GS", "qty": 17, "limit": 897.0}],
            stop={"price": 870.0},
            tg_message_id=42,
            pnl_total=Decimal("12345.67"),
        ),
    ),
    "trade_card_transition": lambda s, c: (
        orm.TradeCardTransition,
        TradeCardTransition(
            card_id=c["card"],
            at=AT,
            from_state="PLANNED",
            to_state="ARMED",
            reason="armed for window",
            payload={"window": "15:30-15:55 ET"},
        ),
    ),
    "plugin": lambda s, c: (
        orm.Plugin,
        Plugin(
            id="mode_c", version="0.1.0", kind="strategy", stage="paper", weight=0.05, enabled=True
        ),
    ),
    "financial_quarter": lambda s, c: (
        orm.FinancialQuarter,
        FinancialQuarter(
            ticker="GS",
            metric="net_income",
            period_start=date(2025, 10, 1),
            period_end=date(2025, 12, 31),
            value=4_100_000_000,
            unit="USD",
            derived=True,
            concept="NetIncomeLoss",
            form="10-K",
            accession="0000886982-26-000050",
            filed=date(2026, 2, 20),
        ),
    ),
    "news_article": lambda s, c: (
        orm.NewsArticle,
        NewsItem(
            id="massive:abc123",
            source="massive",
            published_at=AT,
            title="GS beats estimates",
            url="https://example.com/gs",
            tickers=["GS", "MS"],
            publisher="Example Wire",
            keywords=["earnings"],
            insights=[{"ticker": "GS", "sentiment": "positive"}],
            tags=["management"],
        ),
    ),
}


def test_cases_cover_every_table() -> None:
    assert set(CASES) == EXPECTED_TABLES


@pytest.mark.parametrize("name", sorted(CASES))
def test_entity_roundtrip(session: Session, ctx: dict[str, int], name: str) -> None:
    orm_cls, obj = CASES[name](session, ctx)
    row = _save(session, orm_cls, obj)
    key = inspect(row).identity
    session.expunge_all()
    loaded = session.get(orm_cls, key)
    assert loaded is not None
    restored = type(obj).model_validate(loaded)
    assert restored.model_dump(exclude={"id"}) == obj.model_dump(exclude={"id"})


# --- ограничения ---


def test_second_decision_for_same_event_rejected(session: Session, ctx: dict[str, int]) -> None:
    duplicate = Decision(
        event_id=ctx["event"], status="SKIPPED", reasons=["EDGE_LOW"], decided_at=AT
    )
    with pytest.raises(IntegrityError, match="uq_decision_event_id"):
        _save(session, orm.Decision, duplicate)


def test_second_event_for_same_report_rejected(session: Session, ctx: dict[str, int]) -> None:
    duplicate = Event(ticker="GS", report_date=REPORT_DAY, date_status="projected")
    with pytest.raises(IntegrityError, match="uq_event_ticker_report_date"):
        _save(session, orm.Event, duplicate)


@pytest.mark.parametrize(
    ("sql", "constraint"),
    [
        ("UPDATE trade_card SET state = 'BOGUS' WHERE id = :card", "ck_trade_card_state"),
        ("UPDATE decision SET status = 'MAYBE' WHERE id = :decision", "ck_decision_status"),
        ("UPDATE event SET date_status = 'rumored' WHERE id = :event", "ck_event_date_status"),
        (
            "INSERT INTO plugin (id, version, kind, stage, enabled) "
            "VALUES ('x', '0.1.0', 'agent', 'production', true)",
            "ck_plugin_stage",
        ),
        (
            "INSERT INTO sector_summary (sector_id, as_of, trend) "
            "VALUES ('banks', '2026-10-01', 2)",
            "ck_sector_summary_trend",
        ),
        (
            "INSERT INTO peer_edge (from_ticker, to_ticker) VALUES ('GS', 'GS')",
            "ck_peer_edge_not_self",
        ),
        (
            "INSERT INTO forecast (event_id, stage, model_version, p_up) "
            "VALUES (:event, 'T-3', 'v', 1.5)",
            "ck_forecast_p_up",
        ),
        (
            "INSERT INTO feature_snapshot (event_id, stage, agent_id, agent_version, features) "
            "VALUES (:event, 'T-5', 'a', 'v', '{}')",
            "ck_feature_snapshot_stage",
        ),
    ],
)
def test_check_constraints_reject_bad_values(
    session: Session, ctx: dict[str, int], sql: str, constraint: str
) -> None:
    params = {key: value for key, value in ctx.items() if f":{key}" in sql}
    with pytest.raises(IntegrityError, match=constraint):
        session.execute(text(sql), params)
