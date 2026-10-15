"""Уровень Black Swan по дням из market_level (E2d): что знает решение до открытия."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import models as orm
from core.domain.types import MarketLevel
from core.risk.black_swan import ORDER


def market_level_before(session: Session, day: date) -> MarketLevel | None:
    """Уровень на закрытии последнего торгового дня строго раньше day (известен до открытия)."""
    level = session.scalar(
        select(orm.MarketLevelDay.level)
        .where(orm.MarketLevelDay.day < day)
        .order_by(orm.MarketLevelDay.day.desc())
        .limit(1)
    )
    return next((known for known in ORDER if known == level), None)
