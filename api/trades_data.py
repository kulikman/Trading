"""Сделки из БД для дашборда: закрытые (с итогом) и открытые карточки.

Карточки создаёт исполнитель (T17). До него таблицы пусты, и экраны показывают «нет сделок».
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.db import models as orm

CLOSED_STATES = ("CLOSED", "STOPPED")
OPEN_STATES = ("ARMED", "OPEN", "C_MODE", "CLOSING")


@dataclass(frozen=True)
class ClosedTrade:
    card_id: int
    ticker: str
    mode: str | None
    opened_at: datetime | None
    closed_at: datetime
    pnl: float
    pnl_direction: float | None
    pnl_vol: float | None
    pnl_ivcrush: float | None
    exit_reason: str | None


@dataclass(frozen=True)
class OpenCard:
    card_id: int
    ticker: str
    mode: str | None
    state: str


def closed_trades(session: Session, *, paper: bool) -> list[ClosedTrade]:
    """Закрытые сделки с итогом P&L, по времени закрытия."""
    last = (
        select(
            orm.TradeCardTransition.card_id,
            func.max(orm.TradeCardTransition.at).label("closed_at"),
            func.min(orm.TradeCardTransition.at).label("opened_at"),
        )
        .group_by(orm.TradeCardTransition.card_id)
        .subquery()
    )
    rows = session.execute(
        select(
            orm.TradeCard, orm.Decision.mode, orm.Event.ticker, last.c.closed_at, last.c.opened_at
        )
        .join(orm.Decision, orm.Decision.id == orm.TradeCard.decision_id)
        .join(orm.Event, orm.Event.id == orm.Decision.event_id)
        .join(last, last.c.card_id == orm.TradeCard.id)
        .where(
            orm.TradeCard.paper.is_(paper),
            orm.TradeCard.state.in_(CLOSED_STATES),
            orm.TradeCard.pnl_total.is_not(None),
        )
        .order_by(last.c.closed_at)
    ).all()
    trades = []
    for card, mode, ticker, closed_at, opened_at in rows:
        reason = session.scalars(
            select(orm.TradeCardTransition.reason)
            .where(orm.TradeCardTransition.card_id == card.id)
            .order_by(orm.TradeCardTransition.at.desc())
            .limit(1)
        ).first()
        trades.append(
            ClosedTrade(
                card_id=card.id,
                ticker=ticker,
                mode=mode,
                opened_at=opened_at,
                closed_at=closed_at,
                pnl=float(card.pnl_total),
                pnl_direction=_float(card.pnl_direction),
                pnl_vol=_float(card.pnl_vol),
                pnl_ivcrush=_float(card.pnl_ivcrush),
                exit_reason=reason,
            )
        )
    return trades


def open_cards(session: Session, *, paper: bool) -> list[OpenCard]:
    rows = session.execute(
        select(orm.TradeCard, orm.Decision.mode, orm.Event.ticker)
        .join(orm.Decision, orm.Decision.id == orm.TradeCard.decision_id)
        .join(orm.Event, orm.Event.id == orm.Decision.event_id)
        .where(orm.TradeCard.paper.is_(paper), orm.TradeCard.state.in_(OPEN_STATES))
        .order_by(orm.TradeCard.id)
    ).all()
    return [OpenCard(card.id, ticker, mode, card.state) for card, mode, ticker in rows]


def has_cards(session: Session, *, paper: bool) -> bool:
    first = session.scalars(
        select(orm.TradeCard.id).where(orm.TradeCard.paper.is_(paper)).limit(1)
    ).first()
    return first is not None


def first_card_at(session: Session, *, paper: bool) -> datetime | None:
    return session.scalar(
        select(func.min(orm.TradeCard.created_at)).where(orm.TradeCard.paper.is_(paper))
    )


def _float(value: object) -> float | None:
    return None if value is None else float(str(value))
