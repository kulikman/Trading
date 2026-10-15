"""Машина состояний карточки сделки (SPEC §11, T17).

    PLANNED → ARMED → OPEN → [C_MODE] → CLOSING → CLOSED
                ↓        ↓
           CANCELLED   STOPPED

Каждый переход пишется в trade_card_transition. Переходы идемпотентны: повтор в то же состояние
ничего не делает (второго ордера нет). Переход, ставящий ордер (ARMED — вход, CLOSING — выход),
проверяется session_guard: вне основной сессии — OutsideSessionError, перехода нет.
PLANNED → CANCELLED — наше толкование: решение отменено до ордера (нет цен для paper).
"""

from datetime import datetime

from sqlalchemy.orm import Session

from core.db import models as orm
from core.domain.types import CardState
from core.session_guard import is_regular_session

TRANSITIONS: dict[str, frozenset[str]] = {
    "PLANNED": frozenset({"ARMED", "CANCELLED"}),
    "ARMED": frozenset({"OPEN", "CANCELLED"}),
    "OPEN": frozenset({"C_MODE", "CLOSING", "STOPPED"}),
    "C_MODE": frozenset({"CLOSING", "STOPPED"}),
    "CLOSING": frozenset({"CLOSED"}),
    "CLOSED": frozenset(),
    "CANCELLED": frozenset(),
    "STOPPED": frozenset(),
}
ORDER_STATES = frozenset({"ARMED", "CLOSING"})  # переход ставит ордер
FINAL_STATES = frozenset({"CLOSED", "CANCELLED", "STOPPED"})


class InvalidTransitionError(ValueError):
    """Переход не разрешён схемой SPEC §11."""


class OutsideSessionError(InvalidTransitionError):
    """Ордер вне основной сессии NYSE — переход отклонён (SPEC §11)."""


def start(session: Session, card: orm.TradeCard, at: datetime, reason: str | None) -> None:
    """Первое состояние новой карточки — PLANNED."""
    card.state = "PLANNED"
    session.add(
        orm.TradeCardTransition(
            card_id=card.id, at=at, from_state=None, to_state="PLANNED", reason=reason
        )
    )


def transition(
    session: Session,
    card: orm.TradeCard,
    to: CardState,
    at: datetime,
    reason: str | None,
    *,
    check_session: bool = True,
) -> bool:
    """Перевести карточку в to; False — она уже там (повтор). Нарушение схемы — ошибка.

    check_session=False — только для paper, где ордер не ставится, а переход восстанавливается
    задним числом по ценам архива (время выхода по закрытию — 16:00, вне сессии [open, close)).
    """
    if card.state == to:
        return False
    if to not in TRANSITIONS.get(card.state, frozenset()):
        raise InvalidTransitionError(f"card {card.id}: {card.state} → {to} is not allowed")
    if check_session and to in ORDER_STATES and not is_regular_session(at):
        raise OutsideSessionError(f"card {card.id}: {to} needs an order outside the session ({at})")
    session.add(
        orm.TradeCardTransition(
            card_id=card.id, at=at, from_state=card.state, to_state=to, reason=reason
        )
    )
    card.state = to
    return True
