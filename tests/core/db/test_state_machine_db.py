from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from core.config import load_config
from core.db import models as orm
from core.db.store import sync_universe
from core.domain.types import CardState
from core.state_machine.card import (
    InvalidTransitionError,
    OutsideSessionError,
    start,
    transition,
)

CONFIG = load_config()
IN_SESSION = datetime(2026, 10, 19, 19, 30, tzinfo=UTC)  # 15:30 ET, понедельник
AFTER_CLOSE = datetime(2026, 10, 19, 21, 0, tzinfo=UTC)  # 17:00 ET
SATURDAY = datetime(2026, 10, 17, 15, 0, tzinfo=UTC)


@pytest.fixture
def card(session: Session) -> orm.TradeCard:
    sync_universe(session, CONFIG.universe)
    event = orm.Event(ticker="NFLX", report_date=date(2026, 10, 20), date_status="confirmed")
    session.add(event)
    session.flush()
    decision = orm.Decision(
        event_id=event.id,
        status="ENTERED",
        strategy_id="straddle",
        construction="straddle",
        mode="move",
        decided_at=IN_SESSION,
    )
    session.add(decision)
    session.flush()
    row = orm.TradeCard(decision_id=decision.id, state="PLANNED", paper=True, legs=[])
    session.add(row)
    session.flush()
    start(session, row, IN_SESSION, "сигнал")
    return row


def states(session: Session) -> list[tuple[str | None, str]]:
    rows = session.scalars(select(orm.TradeCardTransition).order_by(orm.TradeCardTransition.id))
    return [(r.from_state, r.to_state) for r in rows]


def test_full_path_and_idempotent_repeat(session: Session, card: orm.TradeCard) -> None:
    full: tuple[CardState, ...] = ("ARMED", "OPEN", "CLOSING", "CLOSED")
    for to in full:
        assert transition(session, card, to, IN_SESSION, None)
    assert transition(session, card, "CLOSED", IN_SESSION, None) is False  # повтор — без записи
    assert states(session) == [
        (None, "PLANNED"),
        ("PLANNED", "ARMED"),
        ("ARMED", "OPEN"),
        ("OPEN", "CLOSING"),
        ("CLOSING", "CLOSED"),
    ]


def test_order_outside_session_is_rejected(session: Session, card: orm.TradeCard) -> None:
    for moment in (AFTER_CLOSE, SATURDAY):
        with pytest.raises(OutsideSessionError):
            transition(session, card, "ARMED", moment, "ордер на вход")
    assert card.state == "PLANNED"
    assert states(session) == [(None, "PLANNED")]  # ордера и перехода нет
    assert transition(session, card, "ARMED", AFTER_CLOSE, None, check_session=False)  # paper


@pytest.mark.parametrize(
    ("path", "bad"),
    [
        ((), "OPEN"),  # без ARMED нет исполнения
        (("ARMED", "OPEN"), "CANCELLED"),  # открытую позицию не отменить — только закрыть
        (("ARMED", "OPEN", "STOPPED"), "CLOSING"),  # из конечного состояния — никуда
    ],
)
def test_forbidden_transitions(
    session: Session, card: orm.TradeCard, path: tuple[CardState, ...], bad: CardState
) -> None:
    for to in path:
        transition(session, card, to, IN_SESSION, None)
    with pytest.raises(InvalidTransitionError):
        transition(session, card, bad, IN_SESSION, None)
