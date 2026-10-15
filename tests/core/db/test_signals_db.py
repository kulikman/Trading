from datetime import UTC, date, datetime

import pytest
from sqlalchemy.orm import Session

from core.config import load_config
from core.db import models as orm
from core.db.store import sync_universe
from execution.cards import open_card
from notify.signals import send_new_signals, signal_text

CONFIG = load_config()
AT = datetime(2026, 10, 20, 19, 10, tzinfo=UTC)


class Bot:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def send(self, text: str) -> int:
        self.texts.append(text)
        return 100 + len(self.texts)


def entry(session: Session, construction: str, strategy: str, mode: str) -> orm.Decision:
    sync_universe(session, CONFIG.universe)
    event = orm.Event(
        ticker="NFLX", report_date=date(2026, 10, 20), report_time="AMC", date_status="confirmed"
    )
    session.add(event)
    session.flush()
    session.add(
        orm.DecisionStep(
            event_id=event.id,
            stage="T-1",
            job="j",
            strategy_id=strategy,
            is_shadow=False,
            outcome="proposal",
            mode=mode,
            construction=construction,
            risk_fraction=0.01,
            at=AT,
        )
    )
    decision = orm.Decision(
        event_id=event.id,
        status="ENTERED",
        strategy_id=strategy,
        construction=construction,
        mode=mode,
        decided_at=AT,
    )
    session.add(decision)
    session.flush()
    open_card(session, decision)
    return decision


def test_condor_message_and_sent_once(session: Session) -> None:
    entry(session, "iron_condor", "iron_condor", "move")
    bot = Bot()
    assert send_new_signals(session, bot, CONFIG.thresholds) == 1
    assert bot.texts[0].splitlines() == [
        "NFLX · отчёт 20.10 после закрытия · iron condor · PAPER",
        "ВХОД   20.10 15:30 ET (22:30 МСК), по закрытию",
        "ВЫХОД  21.10 11:00 ET (18:00 МСК) — не позже; стоп 2× премии, цель 50%",
        "РИСК   1.0% капитала — $1 000",
    ]
    assert send_new_signals(session, bot, CONFIG.thresholds) == 0
    card = session.query(orm.TradeCard).one()
    assert card.tg_message_id == 101


def test_mode_c_message(session: Session) -> None:
    decision = entry(session, "stock_short", "mode_c", "C")
    event = session.get(orm.Event, decision.event_id)
    assert event is not None
    text = signal_text(event, decision, 0.01, CONFIG.thresholds)
    assert text.splitlines()[0] == "NFLX · отчёт 20.10 после закрытия · акция, продажа · PAPER"
    assert "ВХОД   21.10 10:45 ET (17:45 МСК)" in text
    assert "трейлинг 2 × ATR(14)" in text


@pytest.mark.parametrize("state", ["CLOSED", "CANCELLED"])
def test_finished_cards_are_not_announced(session: Session, state: str) -> None:
    entry(session, "straddle", "straddle", "move")
    session.query(orm.TradeCard).one().state = state
    bot = Bot()
    assert send_new_signals(session, bot, CONFIG.thresholds) == 0
