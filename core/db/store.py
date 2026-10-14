"""Запись данных источников в БД. Повторный запуск задачи не создаёт дублей (SPEC §13)."""

from collections.abc import Iterable

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.config.universe import Universe
from core.db import models as orm
from core.domain.earnings import ConsensusSnapshot
from core.domain.financials import FinancialQuarter
from core.domain.news import NewsItem
from core.domain.schedule import EventJob


def save_consensus_snapshots(session: Session, snapshots: Iterable[ConsensusSnapshot]) -> int:
    """Снимок консенсуса на дату. Повтор за ту же дату обновляет значения, а не дублирует строку."""
    rows = [s.model_dump() for s in snapshots]
    if not rows:
        return 0
    statement = insert(orm.ConsensusSnapshot).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["ticker", "fiscal_period", "as_of"],
        set_={
            "eps_estimate": statement.excluded.eps_estimate,
            "rev_estimate": statement.excluded.rev_estimate,
            "updated_at": func.now(),
        },
    )
    session.execute(statement)
    return len(rows)


def save_news(session: Session, items: Iterable[NewsItem]) -> int:
    """Новости: статья уже есть — не трогаем (разметка T14 не затирается). Вернёт число новых."""
    rows = [i.model_dump() for i in items]
    if not rows:
        return 0
    statement = (
        insert(orm.NewsArticle)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(orm.NewsArticle.id)
    )
    return len(session.execute(statement).scalars().all())


def save_financial_quarters(session: Session, quarters: Iterable[FinancialQuarter]) -> int:
    """Кварталы компании. Пересчёт (новая подача) обновляет значение и источник."""
    rows = [q.model_dump() for q in quarters]
    if not rows:
        return 0
    statement = insert(orm.FinancialQuarter).values(rows)
    updated = ("period_start", "value", "unit", "derived", "concept", "form", "accession", "filed")
    statement = statement.on_conflict_do_update(
        index_elements=["ticker", "metric", "period_end"],
        set_={**{c: statement.excluded[c] for c in updated}, "updated_at": func.now()},
    )
    session.execute(statement)
    return len(rows)


def sync_universe(session: Session, universe: Universe) -> None:
    """Сектора, компании и граф информаторов из config/universe.yaml в БД.

    Конфиг — источник названий и состава; оценки strength / lag_days по архиву (T11) не затираются.
    """
    sectors = [
        {
            "id": s.id,
            "name": s.name,
            "key_metrics": s.key_metrics,
            "macro_sensitivity": s.macro_sensitivity,
        }
        for s in universe.sectors
    ]
    statement = insert(orm.Sector).values(sectors)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": statement.excluded.name,
                "key_metrics": statement.excluded.key_metrics,
                "macro_sensitivity": statement.excluded.macro_sensitivity,
                "updated_at": func.now(),
            },
        )
    )
    companies = [
        {"ticker": c.ticker, "sector_id": s.id, "name": c.name}
        for s in universe.sectors
        for c in s.companies
    ]
    statement = insert(orm.Company).values(companies)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["ticker"],
            set_={
                "sector_id": statement.excluded.sector_id,
                "name": statement.excluded.name,
                "updated_at": func.now(),
            },
        )
    )
    if universe.peer_edges:
        edges = [
            {"from_ticker": e.from_ticker, "to_ticker": e.to_ticker} for e in universe.peer_edges
        ]
        session.execute(insert(orm.PeerEdge).values(edges).on_conflict_do_nothing())


def save_event_jobs(session: Session, jobs: Iterable[EventJob]) -> int:
    """План задач события. Повтор обновляет время, а не дублирует; выполненные не трогаются."""
    rows = [j.model_dump() for j in jobs]
    if not rows:
        return 0
    statement = insert(orm.EventJob).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["event_id", "stage", "job"],
        set_={
            "kind": statement.excluded.kind,
            "run_at": statement.excluded.run_at,
            "outside_session": statement.excluded.outside_session,
            "updated_at": func.now(),
        },
        where=orm.EventJob.status == "planned",
    )
    session.execute(statement)
    return len(rows)
