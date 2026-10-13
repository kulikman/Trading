"""Запись данных источников в БД. Повторный запуск задачи не создаёт дублей (SPEC §13)."""

from collections.abc import Iterable

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.db import models as orm
from core.domain.earnings import ConsensusSnapshot
from core.domain.news import NewsItem


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
