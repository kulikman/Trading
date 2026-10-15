from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from core.config import load_config
from core.db import models as orm
from core.db.store import sync_universe
from core.state_machine.card import transition
from execution.cards import open_card
from notify.signals import escort_text, send_new_signals, send_skips, signal_text

CONFIG = load_config()
AT = datetime(2026, 10, 20, 19, 10, tzinfo=UTC)


class Bot:
    def __init__(self) -> None:
        self.texts: list[str] = []
        self.silent: list[bool] = []
        self.edits: list[tuple[int, str]] = []

    def send(
        self,
        text: str,
        *,
        silent: bool = False,
        buttons: list[tuple[str, str]] | None = None,
        reply_to: int | None = None,
    ) -> int:
        self.texts.append(text)
        self.silent.append(silent)
        return 100 + len(self.texts)

    def edit(
        self, message_id: int, text: str, *, buttons: list[tuple[str, str]] | None = None
    ) -> None:
        self.edits.append((message_id, text))


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
        "СТАТУС ждём вход",
    ]
    assert send_new_signals(session, bot, CONFIG.thresholds) == 0
    card = session.query(orm.TradeCard).one()
    assert card.tg_message_id == 101


def test_state_change_edits_the_same_message(session: Session) -> None:
    entry(session, "iron_condor", "iron_condor", "move")
    bot = Bot()
    send_new_signals(session, bot, CONFIG.thresholds)
    card = session.query(orm.TradeCard).one()
    for to in ("ARMED", "OPEN", "CLOSING", "CLOSED"):
        transition(session, card, to, AT, "target" if to == "CLOSED" else None, check_session=False)
    card.pnl_total = Decimal("512.4")
    assert send_new_signals(session, bot, CONFIG.thresholds) == 1
    assert len(bot.texts) == 1  # новое сообщение не отправлено — правка
    message_id, text = bot.edits[0]
    assert message_id == 101
    assert text.splitlines()[-1] == "СТАТУС закрыта (цель) · итог +$512"
    assert send_new_signals(session, bot, CONFIG.thresholds) == 0  # показанное не правится снова


def test_skip_message_silent_once(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    event = orm.Event(
        ticker="NFLX", report_date=date(2026, 10, 20), report_time="AMC", date_status="confirmed"
    )
    session.add(event)
    session.flush()
    session.add_all(
        [
            orm.DecisionStep(
                event_id=event.id,
                stage="T-1",
                job="j",
                strategy_id="straddle",
                is_shadow=False,
                outcome="skip",
                mode="move",
                construction="straddle",
                reasons=["PRE_RUN"],
                at=AT,
            ),
            orm.Decision(
                event_id=event.id, status="SKIPPED", reasons=["PRE_RUN", "EDGE_LOW"], decided_at=AT
            ),
        ]
    )
    session.flush()
    bot = Bot()
    assert send_skips(session, bot) == 1
    assert send_skips(session, bot) == 0
    assert bot.silent == [True]
    assert bot.texts[0].splitlines() == [
        "NFLX · отчёт 20.10 после закрытия · НЕ ВХОДИМ",
        "Причина: PRE_RUN — сильный рост перед отчётом без причины",
        "Доп.: EDGE_LOW — нет сигнала или преимущество не выше издержек",
        "Теневая сделка — посчитается вечером после реакции",
    ]


def test_escort_lists_open_positions(session: Session) -> None:
    entry(session, "stock", "mode_c", "C")
    card = session.query(orm.TradeCard).one()
    assert escort_text(session, AT) is None  # открытых позиций нет
    card.state = "OPEN"
    card.trailing = {"stop": 101.29}
    session.flush()
    assert (
        escort_text(session, AT)
        == "СОПРОВОЖДЕНИЕ · 20.10 15:10 ET (22:10 МСК)\nNFLX · акция · стоп 101.29"
    )


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
