"""Бот Telegram (T18, SPEC §11–12): кнопки карточек, цена исполнения и напоминание.

Отдельный процесс (`python -m notify.bot`, контейнер trading-bot): долгий опрос getUpdates, только
нажатия и ответы из чата заказчика. «Исполнено» — Real-карточка ARMED: бот спрашивает цену
исполнения; ответ на его сообщение (числа по ордерам входа или «лимит») записывает исполнения,
ARMED → OPEN (E10-3). «Не исполнил» — ордера отменяются, ARMED → CANCELLED. «Детали» — состав,
исполнения и история карточки. У paper — только «Детали»: исполнение считает система.
Напоминание: Real-вход не подтверждён execution.fill_reminder_minutes (15) — одно сообщение ответом.
"""

import logging
import time as clock
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from adapters.broker.base import CardOrders
from adapters.broker.factory import create_card_orders
from adapters.errors import DataError
from core.config import load_config
from core.db import models as orm
from core.db.session import create_db_engine
from core.domain.broker import Order, OrderId, Quote
from core.domain.trading import CardFill
from core.session_guard import to_et
from core.state_machine.card import transition
from core.text import plural
from notify.signals import NAMES, Sender, card_buttons
from notify.telegram.client import TelegramClient, TelegramError

logger = logging.getLogger(__name__)


class PendingOrder(Protocol):
    """Ордер к подтверждению (ticket ручного брокера) — то, что нужно боту."""

    @property
    def order_id(self) -> OrderId:
        """Id ордера у брокера."""

    @property
    def order(self) -> Order:
        """Ордер."""

    @property
    def instruction(self) -> str:
        """Строка ордера для человека."""


RETRY_SECONDS = 5


def handle_callback(
    session: Session, data: str, broker: CardOrders, now: datetime, sender: Sender
) -> str:
    """Нажатие кнопки → действие с карточкой; вернуть короткий ответ для всплывающей подсказки."""
    action, _, raw = data.partition(":")
    card = session.get(orm.TradeCard, int(raw)) if raw.isdigit() else None
    if card is None:
        return "Карточка не найдена"
    if action == "details":
        return details_text(session, card)
    if card.paper:
        return "Paper: исполнение считает система"
    if card.state != "ARMED":
        return f"Карточка уже {card.state}"
    tickets = broker.pending_for_card(card.id)
    if action == "fill":  # «Исполнено» — цена исполнения ответом на вопрос бота (E10-3)
        entries = _entries(tickets)
        if not entries:
            return "Нет ордеров входа к подтверждению — проверьте карточку"
        lines = [f"{n}) {t.instruction}" for n, t in enumerate(entries, start=1)]
        card.fill_prompt_id = sender.send(
            "Цена исполнения? Ответьте на это сообщение: "
            f"{len(entries)} {plural(len(entries), 'цена', 'цены', 'цен')} через пробел "
            "по порядку или «лимит».\n" + "\n".join(lines),
            reply_to=card.tg_message_id,
        )
        return "Ответьте ценой исполнения"
    if action == "skip":
        for ticket in tickets:
            broker.cancel(ticket.order_id)
        card.fill_prompt_id = None
        transition(session, card, "CANCELLED", now, "не исполнил (кнопка)", check_session=False)
        return "Вход отменён — снимите ордера у брокера"
    return "Неизвестная кнопка"


def handle_reply(
    session: Session, text: str, reply_to: int, broker: CardOrders, now: datetime
) -> str | None:
    """Ответ на «Цена исполнения?» → исполнения по фактическим ценам, ARMED → OPEN.

    Числа — по одному на ордер входа, в порядке вопроса (запятая или точка); «лимит» — по ценам
    лимитов. Не ответ на вопрос бота — None (сообщение не про исполнение).
    """
    card = session.scalars(
        select(orm.TradeCard).where(orm.TradeCard.fill_prompt_id == reply_to)
    ).first()
    if card is None:
        return None
    if card.state != "ARMED":
        return f"Карточка уже {card.state}"
    entries = _entries(broker.pending_for_card(card.id))
    prices = _prices(text, entries)
    if isinstance(prices, str):
        return prices
    fills = [
        broker.confirm_fill(t.order_id, price=p, at=now)
        for t, p in zip(entries, prices, strict=True)
    ]
    card.fills = [
        *(card.fills or []),
        *(
            CardFill(
                symbol=f.symbol,
                side=f.side,
                quantity=f.quantity,
                price=f.price,
                at=f.at,
                purpose="entry",
            ).model_dump(mode="json")
            for f in fills
        ),
    ]
    card.fill_prompt_id = None
    transition(session, card, "OPEN", now, "исполнено (цена ответом)", check_session=False)
    return "Исполнение записано: " + ", ".join(f"{p:.2f}" for p in prices)


def _entries[T: PendingOrder](tickets: Sequence[T]) -> list[T]:
    """Ордера входа в порядке карточки (client_order_id … -0, -1, …)."""

    def position(ticket: PendingOrder) -> int:
        tail = ticket.order.client_order_id.rsplit("-", 1)[-1]
        return int(tail) if tail.isdigit() else 0

    return sorted((t for t in tickets if t.order.purpose == "entry"), key=position)


def _prices(text: str, entries: Sequence[PendingOrder]) -> list[float] | str:
    words = text.replace(";", " ").split()
    if [w.lower() for w in words] in (["лимит"], ["limit"], ["как", "лимит"]):
        limits = [t.order.limit_price or t.order.stop_price for t in entries]
        if any(p is None for p in limits):
            return "У ордера нет цены лимита — укажите цену числом"
        return [float(p or 0) for p in limits]
    try:
        prices = [float(w.replace(",", ".")) for w in words]
    except ValueError:
        return f"Не понял цену: «{text[:40]}». Нужны числа через пробел или «лимит»"
    if len(prices) != len(entries):
        need = f"{len(entries)} {plural(len(entries), 'цена', 'цены', 'цен')}"
        return f"Нужно {need}, получено {len(prices)}"
    if any(p <= 0 for p in prices):
        return "Цена должна быть больше нуля"
    return prices


def details_text(session: Session, card: orm.TradeCard) -> str:
    """«Детали»: ноги, исполнения и переходы карточки (коротко — для всплывающей подсказки)."""
    decision = session.get(orm.Decision, card.decision_id)
    name = NAMES.get(decision.construction or "", "") if decision else ""
    legs = ", ".join(
        f"{leg['side']} {leg['symbol']} ×{leg['quantity']:g}" for leg in card.legs or []
    )
    path = " → ".join(
        session.scalars(
            select(orm.TradeCardTransition.to_state)
            .where(orm.TradeCardTransition.card_id == card.id)
            .order_by(orm.TradeCardTransition.id)
        ).all()
    )
    return f"#{card.id} {name}: {legs or 'ног нет'}. {path}"


def send_reminders(session: Session, client: Sender, now: datetime, remind_after: timedelta) -> int:
    """Real-вход не подтверждён remind_after — одно напоминание ответом на карточку."""
    rows = session.execute(
        select(orm.TradeCard, orm.Event)
        .join(orm.Decision, orm.Decision.id == orm.TradeCard.decision_id)
        .join(orm.Event, orm.Event.id == orm.Decision.event_id)
        .where(
            orm.TradeCard.paper.is_(False),
            orm.TradeCard.state == "ARMED",
            orm.TradeCard.reminded_at.is_(None),
        )
    ).all()
    sent = 0
    for card, event in rows:
        armed_at = session.scalar(
            select(orm.TradeCardTransition.at)
            .where(
                orm.TradeCardTransition.card_id == card.id,
                orm.TradeCardTransition.to_state == "ARMED",
            )
            .order_by(orm.TradeCardTransition.id.desc())
            .limit(1)
        )
        if armed_at is None or now - armed_at < remind_after:
            continue
        et = to_et(armed_at)
        client.send(
            f"Напоминание · {event.ticker}: исполнение не подтверждено с {et:%H:%M} ET",
            buttons=card_buttons(card),
            reply_to=card.tg_message_id,
        )
        card.reminded_at = now
        session.commit()
        sent += 1
    return sent


def main() -> int:  # pragma: no cover — процесс с сетью; логика — в функциях выше
    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # в адресе запроса — токен бота
    client = TelegramClient.from_env()
    if client is None:
        logger.error("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы — бот не запущен")
        return 1

    def no_quotes(symbol: str) -> Quote:
        raise DataError("broker", f"ручной брокер: котировки {symbol} нет")

    db = create_db_engine()
    broker = create_card_orders(
        quote_source=no_quotes,
        no_market_orders_first_minutes=load_config().thresholds.execution.no_market_orders_first_minutes,
        session_factory=lambda: Session(db),
    )
    offset: int | None = None
    logger.info("bot started")
    while True:
        try:
            updates = client.updates(offset)
        except TelegramError:
            logger.exception("getUpdates failed")
            clock.sleep(RETRY_SECONDS)
            continue
        for update in updates:
            update_id = update.get("update_id")
            offset = update_id + 1 if isinstance(update_id, int) else offset
            message = update.get("message")
            if isinstance(message, dict):
                _on_message(db, client, broker, message)
                continue
            query = update.get("callback_query")
            if not isinstance(query, dict):
                continue
            chat = (query.get("message") or {}).get("chat", {}).get("id")
            if str(chat) != client.chat_id:
                logger.warning("callback from a foreign chat ignored")
                continue
            with Session(db) as session, session.begin():
                reply = handle_callback(
                    session, str(query.get("data", "")), broker, datetime.now(UTC), client
                )
            client.answer(str(query.get("id")), reply)


def _on_message(
    db: Engine, client: TelegramClient, broker: CardOrders, message: dict[str, Any]
) -> None:  # pragma: no cover — сеть; логика — handle_reply
    """Ответ заказчика на вопрос о цене исполнения; остальные сообщения не трогаем."""
    if str((message.get("chat") or {}).get("id")) != client.chat_id:
        return
    original = message.get("reply_to_message") or {}
    reply_to, text = original.get("message_id"), message.get("text")
    if not isinstance(reply_to, int) or not isinstance(text, str):
        return
    with Session(db) as session, session.begin():
        answer = handle_reply(session, text, reply_to, broker, datetime.now(UTC))
    if answer is not None:
        client.send(answer, reply_to=message.get("message_id"))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
