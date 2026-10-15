"""Бот Telegram (T18, SPEC §11–12): кнопки карточек и напоминание о неподтверждённом исполнении.

Отдельный процесс (`python -m notify.bot`, контейнер trading-bot): долгий опрос getUpdates, только
нажатия из чата заказчика. «Исполнено» — Real-карточка ARMED: ордера подтверждаются по цене
лимита (стопа), ARMED → OPEN; «Не исполнил» — ордера отменяются, ARMED → CANCELLED; «Детали» —
состав, исполнения и история карточки. У paper — только «Детали»: исполнение считает система.
Напоминание: Real-вход не подтверждён execution.fill_reminder_minutes (15) — одно сообщение ответом.
"""

import logging
import time as clock
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.broker.base import CardOrders
from adapters.broker.factory import create_card_orders
from adapters.errors import DataError
from core.config import load_config
from core.db import models as orm
from core.domain.broker import Quote
from core.domain.trading import CardFill
from core.session_guard import to_et
from core.state_machine.card import transition
from notify.signals import NAMES, Sender, card_buttons
from notify.telegram.client import TelegramClient, TelegramError

logger = logging.getLogger(__name__)

RETRY_SECONDS = 5


def handle_callback(session: Session, data: str, broker: CardOrders, now: datetime) -> str:
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
    if action == "fill":
        priced = [(t, t.order.limit_price or t.order.stop_price) for t in tickets]
        if not priced or any(p is None for _, p in priced):
            return "Нет ордеров с ценой к подтверждению — проверьте карточку"
        fills = [broker.confirm_fill(t.order_id, price=float(p or 0), at=now) for t, p in priced]
        card.fills = [
            *(card.fills or []),
            *(
                CardFill(
                    symbol=f.symbol,
                    side=f.side,
                    quantity=f.quantity,
                    price=f.price,
                    at=f.at,
                    purpose=t.order.purpose,
                ).model_dump(mode="json")
                for t, f in zip((t for t, _ in priced), fills, strict=True)
            ),
        ]
        transition(session, card, "OPEN", now, "исполнено (кнопка)", check_session=False)
        return "Исполнение подтверждено"
    if action == "skip":
        for ticket in tickets:
            broker.cancel(ticket.order_id)
        transition(session, card, "CANCELLED", now, "не исполнил (кнопка)", check_session=False)
        return "Вход отменён"
    return "Неизвестная кнопка"


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
    from core.scheduler.jobs import engine

    logging.basicConfig(level=logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)  # в адресе запроса — токен бота
    client = TelegramClient.from_env()
    if client is None:
        logger.error("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID не заданы — бот не запущен")
        return 1

    def no_quotes(symbol: str) -> Quote:
        raise DataError("broker", f"ручной брокер: котировки {symbol} нет")

    broker = create_card_orders(
        quote_source=no_quotes,
        no_market_orders_first_minutes=load_config().thresholds.execution.no_market_orders_first_minutes,
        session_factory=lambda: Session(engine()),
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
            query = update.get("callback_query")
            if not isinstance(query, dict):
                continue
            chat = (query.get("message") or {}).get("chat", {}).get("id")
            if str(chat) != client.chat_id:
                logger.warning("callback from a foreign chat ignored")
                continue
            with Session(engine()) as session, session.begin():
                reply = handle_callback(
                    session, str(query.get("data", "")), broker, datetime.now(UTC)
                )
            client.answer(str(query.get("id")), reply)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
