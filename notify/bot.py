"""Бот Telegram (T18, SPEC §11–12): кнопки карточек, цена исполнения и напоминание.

Отдельный процесс (`python -m notify.bot`, контейнер trading-bot): долгий опрос getUpdates, только
нажатия и ответы из чата заказчика. «Исполнено» — Real-карточка ARMED: бот спрашивает цену
исполнения; ответ на его сообщение (числа по ордерам входа или «лимит») записывает исполнения,
ARMED → OPEN (E10-3). «Не исполнил» — ордера отменяются, ARMED → CANCELLED. «Детали» — состав,
исполнения и история карточки. У paper — только «Детали»: исполнение считает система.
Напоминание: Real-вход не подтверждён execution.fill_reminder_minutes (15) — одно сообщение ответом.
"""

import logging
import math
import time as clock
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from adapters.broker.base import CardOrders
from adapters.broker.factory import create_card_orders, create_cost_model
from adapters.errors import DataError
from core.config import load_config
from core.db import models as orm
from core.db.session import create_db_engine
from core.domain.broker import Order, OrderId, Quote, Side
from core.domain.trading import CardFill, CardLeg
from core.session_guard import to_et
from core.state_machine.card import transition
from core.text import plural
from execution.costs import CostLeg, CostModel
from notify.signals import NAMES, Sender, card_buttons
from notify.telegram.client import TelegramClient, TelegramError

logger = logging.getLogger(__name__)

SIDE_WORD = {"buy": "Купить", "sell": "Продать"}
OPEN_STATES = ("OPEN", "C_MODE")  # позиция у брокера — «Закрыл» записывает выход


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
    if action == "exit":  # «Закрыл» — Real OPEN: цены выхода по ногам ответом (E10-3)
        if card.state not in OPEN_STATES:
            return f"Карточка уже {card.state}"
        legs = [CardLeg.model_validate(leg, strict=False) for leg in card.legs or []]
        lines = [
            f"{n}) {SIDE_WORD[_reverse(leg.side)]}  {leg.symbol}  {leg.quantity:g} шт."
            for n, leg in enumerate(legs, start=1)
        ]
        card.fill_prompt_id = sender.send(
            "Цена выхода? Ответьте на это сообщение: "
            f"{len(legs)} {plural(len(legs), 'цена', 'цены', 'цен')} через пробел по порядку.\n"
            + "\n".join(lines),
            reply_to=card.tg_message_id,
        )
        return "Ответьте ценой выхода"
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
    session: Session,
    text: str,
    reply_to: int,
    broker: CardOrders,
    now: datetime,
    costs: CostModel | None = None,
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
    if card.state in OPEN_STATES:
        return _close(session, card, text, broker, now, costs)
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


def _close(
    session: Session,
    card: orm.TradeCard,
    text: str,
    broker: CardOrders,
    now: datetime,
    costs: CostModel | None,
) -> str:
    """Цены выхода по ногам → исполнения выхода, P&L, стоп-ордер снят, карточка закрыта."""
    legs = [CardLeg.model_validate(leg, strict=False) for leg in card.legs or []]
    prices = _numbers(text, len(legs))
    if isinstance(prices, str):
        return prices
    entries = {
        f["symbol"]: float(f["price"]) for f in card.fills or [] if f.get("purpose") == "entry"
    }
    if any(leg.symbol not in entries for leg in legs):
        return "Нет цены входа по одной из ног — проверьте карточку"
    gross = commission = 0.0
    exits = []
    for leg, price in zip(legs, prices, strict=True):
        sign = 1 if leg.side == "buy" else -1
        gross += sign * (price - entries[leg.symbol]) * leg.quantity * leg.multiplier
        if costs is not None:
            for at in (entries[leg.symbol], price):
                cost_leg = CostLeg(leg.instrument, int(leg.quantity), leg.multiplier, at)
                commission += costs.leg_cost(cost_leg, at_open=False).commission
        exits.append(
            CardFill(
                symbol=leg.symbol,
                side=_reverse(leg.side),
                quantity=leg.quantity,
                price=price,
                at=now,
                purpose="exit",
            ).model_dump(mode="json")
        )
    for ticket in broker.pending_for_card(card.id):
        broker.cancel(ticket.order_id)  # стоп больше не нужен — позиции нет
    card.fills = [*(card.fills or []), *exits]
    card.costs = Decimal(str(round(commission, 4)))
    card.pnl_total = Decimal(str(round(gross - commission, 4)))
    card.fill_prompt_id = None
    if _stopped(card, legs, prices):
        transition(session, card, "STOPPED", now, "стоп (цена ответом)", check_session=False)
    else:
        transition(session, card, "CLOSING", now, "закрыто (цена ответом)", check_session=False)
        transition(session, card, "CLOSED", now, "закрыто (цена ответом)", check_session=False)
    return f"Закрыто: итог {'+' if gross - commission >= 0 else '−'}${abs(gross - commission):,.0f}"


def _stopped(card: orm.TradeCard, legs: Sequence[CardLeg], prices: Sequence[float]) -> bool:
    """Акция вышла по стопу: цена выхода не лучше уровня стопа (трейлинг или стартовый)."""
    stop = (card.trailing or {}).get("stop") or (card.stop or {}).get("price")
    if stop is None or len(legs) != 1 or legs[0].instrument != "stock":
        return False
    level = float(stop)
    return prices[0] <= level if legs[0].side == "buy" else prices[0] >= level


def _reverse(side: Side) -> Side:
    return "sell" if side == "buy" else "buy"


def _numbers(text: str, count: int) -> list[float] | str:
    try:
        prices = [_parse_price(w) for w in text.replace(";", " ").split()]
    except ValueError:
        return f"Не понял цену: «{text[:40]}». Нужны числа через пробел"
    if len(prices) != count:
        need = f"{count} {plural(count, 'цена', 'цены', 'цен')}"
        return f"Нужно {need}, получено {len(prices)}"
    if any(p <= 0 for p in prices):
        return "Цена должна быть больше нуля"
    if any(not math.isfinite(p) for p in prices):
        return "Цена должна быть конечным числом"
    return prices


def _parse_price(word: str) -> float:
    """Число с поддержкой запятой: «1,23» → 1.23 (евро), «1,234.56» → 1234.56 (тысячи)."""
    if "." in word:
        # Есть точка → запятые разделители тысяч
        value = float(word.replace(",", ""))
    elif word.count(",") == 1:
        # Одна запятая, нет точки → десятичная запятая (европейский стиль)
        value = float(word.replace(",", "."))
    else:
        # Несколько запятых → разделители тысяч
        value = float(word.replace(",", ""))
    if not math.isfinite(value):
        raise ValueError(f"не конечное число: {word}")
    return value


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
    found = _numbers(text, len(entries))
    if isinstance(found, str) and found.startswith("Не понял"):
        return found + " или «лимит»"
    return found


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
    costs = create_cost_model(load_config().broker)
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
            try:
                message = update.get("message")
                if isinstance(message, dict):
                    _on_message(db, client, broker, costs, message)
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
            except Exception:
                logger.exception("error processing update %s", update_id)


def _on_message(
    db: Engine,
    client: TelegramClient,
    broker: CardOrders,
    costs: CostModel,
    message: dict[str, Any],
) -> None:  # pragma: no cover — сеть; логика — handle_reply
    """Ответ заказчика на вопрос о цене исполнения; остальные сообщения не трогаем."""
    if str((message.get("chat") or {}).get("id")) != client.chat_id:
        return
    original = message.get("reply_to_message") or {}
    reply_to, text = original.get("message_id"), message.get("text")
    if not isinstance(reply_to, int) or not isinstance(text, str):
        return
    with Session(db) as session, session.begin():
        answer = handle_reply(session, text, reply_to, broker, datetime.now(UTC), costs)
    if answer is not None:
        client.send(answer, reply_to=message.get("message_id"))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
