from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from core.config import load_config
from core.db import models as orm
from core.db.store import sync_universe
from core.registry.state import sync_plugins
from notify.digest import exit_texts, terminal_text

CONFIG = load_config()
AT = datetime(2026, 10, 21, 14, 45, tzinfo=UTC)


def event(session: Session) -> orm.Event:
    sync_universe(session, CONFIG.universe)
    sync_plugins(session, CONFIG.registry)
    row = orm.Event(
        ticker="NFLX", report_date=date(2026, 10, 20), report_time="AMC", date_status="confirmed"
    )
    session.add(row)
    session.flush()
    return row


def test_exit_text_for_open_real_straddle(session: Session) -> None:
    row = event(session)
    decision = orm.Decision(
        event_id=row.id,
        status="ENTERED",
        reasons=[],
        mode="move",
        strategy_id="straddle",
        construction="straddle",
        decided_at=AT,
    )
    session.add(decision)
    session.flush()
    legs = [
        {
            "symbol": "O:NFLX261023C00100000",
            "instrument": "option",
            "side": "buy",
            "quantity": 2.0,
            "multiplier": 100,
        },
        {
            "symbol": "O:NFLX261023P00100000",
            "instrument": "option",
            "side": "buy",
            "quantity": 2.0,
            "multiplier": 100,
        },
    ]
    card = orm.TradeCard(decision_id=decision.id, state="OPEN", paper=False, legs=legs)
    paper = orm.TradeCard(decision_id=decision.id, state="OPEN", paper=True, legs=legs)
    session.add_all([card, paper])
    session.flush()
    assert exit_texts(session, row.id) == [
        f"ВЫХОД до 11:00 ET · NFLX · стрэддл · REAL #{card.id}\n"
        "Продать  O:NFLX261023C00100000  2 шт.\n"
        "Продать  O:NFLX261023P00100000  2 шт.\n"
        "Закрыли — нажмите «Закрыл» в карточке и ответьте ценами выхода"
    ]


def test_terminal_for_live_mode_c_without_card(session: Session) -> None:
    row = event(session)
    assert terminal_text(session, row) is None  # режим C в paper — человеку делать нечего
    plugin = session.get(orm.Plugin, ("mode_c", "0.1.0"))
    assert plugin is not None
    plugin.stage = "live"
    session.flush()
    text = terminal_text(session, row)
    assert text is not None
    assert text.startswith("БЫТЬ У ТЕРМИНАЛА · NFLX · режим C (Real)")
