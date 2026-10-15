"""Карточки сделок (SPEC §11): создание и переходы состояний с журналом переходов."""

from datetime import datetime

from sqlalchemy.orm import Session

from core.db import models as orm


def open_card(session: Session, decision: orm.Decision) -> orm.TradeCard:
    """Карточка paper-сделки для нового входа: PLANNED с момента решения."""
    card = orm.TradeCard(decision_id=decision.id, state="PLANNED", paper=True, legs=[])
    session.add(card)
    session.flush()
    move(session, card, "PLANNED", decision.decided_at, "сигнал")
    return card


def move(session: Session, card: orm.TradeCard, to: str, at: datetime, reason: str | None) -> None:
    """Переход карточки в состояние to с записью в trade_card_transition."""
    session.add(
        orm.TradeCardTransition(
            card_id=card.id,
            at=at,
            from_state=None if to == "PLANNED" else card.state,
            to_state=to,
            reason=reason,
        )
    )
    card.state = to
