from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from core.config import load_config
from core.db import models as orm
from core.db.store import sync_universe
from core.domain.schedule import EventJob
from notify.digest import evening_text, morning_text, notify_handlers, terminal_text

CONFIG = load_config()
MONDAY = datetime(2026, 10, 19, 12, 30, tzinfo=UTC)  # 08:30 ET понедельник


class Bot:
    def __init__(self) -> None:
        self.texts: list[str] = []

    def send(self, text: str, *, silent: bool = False) -> int:
        self.texts.append(text)
        return len(self.texts)


def event(session: Session, ticker: str, day: date, when: str = "BMO") -> orm.Event:
    row = orm.Event(ticker=ticker, report_date=day, report_time=when, date_status="confirmed")
    session.add(row)
    session.flush()
    return row


def card(
    session: Session,
    ev: orm.Event,
    state: str,
    *,
    paper: bool = True,
    pnl: str | None = None,
    construction: str = "iron_condor",
) -> orm.TradeCard:
    decision = orm.Decision(
        event_id=ev.id,
        status="ENTERED",
        strategy_id=construction,
        construction=construction,
        mode="move",
        decided_at=MONDAY,
    )
    session.add(decision)
    session.flush()
    row = orm.TradeCard(
        decision_id=decision.id,
        state=state,
        paper=paper,
        legs=[],
        pnl_total=None if pnl is None else Decimal(pnl),
    )
    session.add(row)
    session.flush()
    return row


def test_monday_morning_digest(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    nflx = event(session, "NFLX", date(2026, 10, 19))
    event(session, "TSLA", date(2026, 10, 21), "AMC")
    friday = event(session, "GS", date(2026, 10, 16))
    closed = card(session, friday, "CLOSED", pnl="512.4")
    session.add(
        orm.TradeCardTransition(
            card_id=closed.id,
            at=datetime(2026, 10, 16, 15, 0, tzinfo=UTC),
            from_state="CLOSING",
            to_state="CLOSED",
            reason="target",
        )
    )
    card(session, nflx, "OPEN")
    session.flush()
    lines = morning_text(session, MONDAY, CONFIG.thresholds).splitlines()
    assert lines[0] == "ДАЙДЖЕСТ · утро · 19.10 08:30 ET (15:30 МСК)"
    assert "19.10 NFLX · до открытия · вход" in lines
    assert "NFLX · iron condor · PAPER" in lines  # открытая позиция
    assert "GS · iron condor · target · +$512" in lines  # закрыто в пятницу
    assert "Неделя 19.10–23.10:" in lines
    assert "21.10 TSLA · после закрытия · ждём решения" in lines
    assert "PAPER: сделок 1, итог +$512" in lines  # итог прошлой недели


def test_evening_digest_and_empty_sections(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    event(session, "TSLA", date(2026, 10, 20), "AMC")
    evening = datetime(2026, 10, 19, 20, 30, tzinfo=UTC)
    lines = evening_text(session, evening).splitlines()
    assert lines[0] == "ДАЙДЖЕСТ · вечер · 19.10 16:30 ET (23:30 МСК)"
    assert lines[1:4] == ["", "Закрыто сегодня:", "—"]
    assert "20.10 TSLA · после закрытия · ждём решения" in lines


def test_terminal_only_for_real_entries(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    nflx = event(session, "NFLX", date(2026, 10, 20), "AMC")
    card(session, nflx, "OPEN")
    assert terminal_text(session, nflx) is None  # paper — человек не нужен
    card(session, nflx, "ARMED", paper=False, construction="straddle")
    text = terminal_text(session, nflx)
    assert text == (
        "БЫТЬ У ТЕРМИНАЛА · NFLX · стрэддл\n"
        "21.10 09:30 ET (16:30 МСК): стоп-гэп на открытии, выходы до 11:00"
    )
    bot = Bot()
    handlers = notify_handlers(lambda: bot)
    job = EventJob(event_id=nflx.id, stage="T0", job="be_at_terminal", kind="notify", run_at=MONDAY)
    handlers["be_at_terminal"](session, job)
    handlers["evening_digest"](session, job)  # общий вечерний дайджест — отдельного сообщения нет
    assert bot.texts == [text]
