from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.broker.manual import ManualBroker
from adapters.broker.order_store import DbOrderStore
from core.config import load_config
from core.db import models as orm
from core.db.store import sync_universe
from core.domain.broker import Order, Quote
from core.state_machine.card import start, transition
from notify.bot import details_text, handle_callback, send_reminders

CONFIG = load_config()
ARMED_AT = datetime(2026, 10, 20, 19, 30, tzinfo=UTC)  # 15:30 ET


class Bot:
    def __init__(self) -> None:
        self.sent: list[tuple[str, list[tuple[str, str]] | None, int | None]] = []

    def send(
        self,
        text: str,
        *,
        silent: bool = False,
        buttons: list[tuple[str, str]] | None = None,
        reply_to: int | None = None,
    ) -> int:
        self.sent.append((text, buttons, reply_to))
        return len(self.sent)

    def edit(
        self, message_id: int, text: str, *, buttons: list[tuple[str, str]] | None = None
    ) -> None:
        raise AssertionError("not used")


def broker(session: Session) -> ManualBroker:
    return ManualBroker(
        quote_source=lambda s: Quote(symbol=s, bid=1, ask=1.1, at=ARMED_AT),
        no_market_orders_first_minutes=5,
        clock=lambda: ARMED_AT,
        store=DbOrderStore(
            lambda: Session(bind=session.connection(), join_transaction_mode="create_savepoint")
        ),
    )


def real_card(session: Session, paper: bool = False, ticker: str = "NFLX") -> orm.TradeCard:
    sync_universe(session, CONFIG.universe)
    event = orm.Event(
        ticker=ticker, report_date=date(2026, 10, 20), report_time="AMC", date_status="confirmed"
    )
    session.add(event)
    session.flush()
    decision = orm.Decision(
        event_id=event.id,
        status="ENTERED",
        strategy_id="mode_c",
        construction="stock",
        mode="C",
        decided_at=ARMED_AT,
    )
    session.add(decision)
    session.flush()
    card = orm.TradeCard(
        decision_id=decision.id,
        state="PLANNED",
        paper=paper,
        legs=[
            {
                "symbol": "NFLX",
                "instrument": "stock",
                "side": "buy",
                "quantity": 10,
                "multiplier": 1,
            }
        ],
        tg_message_id=55,
    )
    session.add(card)
    session.flush()
    start(session, card, ARMED_AT, "сигнал")
    transition(session, card, "ARMED", ARMED_AT, "ордер на вход")
    session.flush()
    return card


def order(card_id: int) -> Order:
    return Order(
        client_order_id=f"card-{card_id}-leg-1",
        symbol="NFLX",
        instrument="stock",
        side="buy",
        quantity=10,
        multiplier=1,
        order_type="limit",
        purpose="entry",
        limit_price=101.5,
    )


def test_fill_button_confirms_orders_and_opens_card(session: Session) -> None:
    card = real_card(session)
    b = broker(session)
    b.place_for_card(order(card.id), card.id)
    assert handle_callback(session, f"fill:{card.id}", b, ARMED_AT) == "Исполнение подтверждено"
    assert card.state == "OPEN"
    assert [(f["purpose"], f["price"]) for f in card.fills or []] == [("entry", 101.5)]
    assert session.scalars(select(orm.BrokerOrder.status)).one() == "filled"
    assert handle_callback(session, f"fill:{card.id}", b, ARMED_AT) == "Карточка уже OPEN"  # повтор


def test_skip_button_cancels(session: Session) -> None:
    card = real_card(session)
    b = broker(session)
    b.place_for_card(order(card.id), card.id)
    assert (
        handle_callback(session, f"skip:{card.id}", b, ARMED_AT)
        == "Вход отменён — снимите ордера у брокера"
    )
    assert card.state == "CANCELLED"
    assert session.scalars(select(orm.BrokerOrder.status)).one() == "cancelled"


def test_paper_details_and_unknown(session: Session) -> None:
    card = real_card(session, paper=True)
    b = broker(session)
    assert (
        handle_callback(session, f"fill:{card.id}", b, ARMED_AT)
        == "Paper: исполнение считает система"
    )
    assert details_text(session, card) == f"#{card.id} акция: buy NFLX ×10. PLANNED → ARMED"
    assert handle_callback(session, "fill:999999", b, ARMED_AT) == "Карточка не найдена"
    real = real_card(session, ticker="TSLA")
    assert handle_callback(session, f"fill:{real.id}", b, ARMED_AT).startswith(
        "Нет ордеров"
    )  # ордеров нет


def test_reminder_once_after_threshold(session: Session) -> None:
    card = real_card(session)
    bot = Bot()
    after = timedelta(minutes=15)
    assert send_reminders(session, bot, ARMED_AT + timedelta(minutes=10), after) == 0
    assert send_reminders(session, bot, ARMED_AT + timedelta(minutes=16), after) == 1
    assert send_reminders(session, bot, ARMED_AT + timedelta(minutes=30), after) == 0  # один раз
    text, buttons, reply_to = bot.sent[0]
    assert text == "Напоминание · NFLX: исполнение не подтверждено с 15:30 ET"
    assert reply_to == 55
    assert buttons is not None
    assert [label for label, _ in buttons] == ["Исполнено", "Не исполнил", "Детали"]
    assert card.reminded_at == ARMED_AT + timedelta(minutes=16)
