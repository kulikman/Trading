"""Сообщения о сделках (SPEC §12, T18): ДЕЙСТВИЕ, ПРОПУСК, СОПРОВОЖДЕНИЕ. Время — ET и МСК.

Одна карточка — одно сообщение: при смене состояния текст правится (строка «СТАТУС»), а не
отправляется заново. ПРОПУСК и СОПРОВОЖДЕНИЕ — без звука. Отправленное помечается и не повторяется.
"""

from collections.abc import Sequence
from datetime import date, datetime, time
from typing import Protocol
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.massive.history import EventDays
from core.config.thresholds import Thresholds
from core.db import models as orm
from core.domain.trading import CardFill, CardPlan
from core.registry.agent_jobs import REPORT_TIMES
from core.session_guard import ET, reaction_day, to_et

MSK = ZoneInfo("Europe/Moscow")
STOCK_CONSTRUCTIONS = ("stock", "stock_short")
REPORT_WORDS = {"BMO": "до открытия", "AMC": "после закрытия", "DURING": "во время сессии"}
NAMES = {
    "straddle": "стрэддл",
    "iron_condor": "iron condor",
    "stock": "акция",
    "stock_short": "акция, продажа",
}


# Коды пропуска словами (SPEC §10) — для сообщения «ПРОПУСК».
REASON_WORDS = {
    "EDGE_LOW": "нет сигнала или преимущество не выше издержек",
    "CONF_LOW": "уверенность модели ниже порога",
    "PRE_RUN": "сильный рост перед отчётом без причины",
    "PEER_CONFLICT": "сектор против направления",
    "CALIBRATION": "компания в карантине калибровки",
    "MACRO_BLOCK": "Black Swan: вход запрещён",
    "C_NOT_CONFIRMED": "сюрприз не подтвердился ценой и объёмом",
    "DATA_MASSIVE": "нет данных Massive",
    "DATA_FINNHUB": "нет данных Finnhub",
    "DATA_ALPHAVANTAGE": "нет данных Alpha Vantage",
    "DATA_BROKER": "нет данных брокера",
    "DATA_CALENDAR": "решение не принималось (календарь)",
    "DATA_MISMATCH": "цена расходится с брокером",
}
STOP_REASONS = {
    "stop": "стоп",
    "trail_stop": "трейлинг-стоп",
    "target": "цель",
    "time": "время",
    "sma": "ниже SMA",
    "max_hold": "срок",
}


class Sender(Protocol):
    def send(
        self,
        text: str,
        *,
        silent: bool = False,
        buttons: list[tuple[str, str]] | None = None,
        reply_to: int | None = None,
    ) -> int:
        """Отправить сообщение; вернуть его id."""

    def edit(
        self, message_id: int, text: str, *, buttons: list[tuple[str, str]] | None = None
    ) -> None:
        """Изменить текст и кнопки сообщения."""


def card_buttons(card: orm.TradeCard) -> list[tuple[str, str]]:
    """Кнопки карточки (SPEC §12): Real ждёт входа — подтвердить / не исполнил; открыта — закрыл."""
    details = ("Детали", f"details:{card.id}")
    if not card.paper and card.state == "ARMED":
        return [("Исполнено", f"fill:{card.id}"), ("Не исполнил", f"skip:{card.id}"), details]
    if not card.paper and card.state in ("OPEN", "C_MODE"):
        return [("Закрыл", f"exit:{card.id}"), details]  # цена выхода ответом (E10-3)
    return [details]


def signal_text(
    event: orm.Event,
    decision: orm.Decision,
    risk_fraction: float,
    thresholds: Thresholds,
    card: orm.TradeCard | None = None,
    exit_reason: str | None = None,
    instructions: Sequence[str] = (),
) -> str:
    """Текст сообщения о входе: что, когда войти, когда выйти, сколько под риском.

    Real: строки ордеров для брокера (ручной брокер, SPEC §12) и риск карточки в $.
    """
    days = EventDays.of(event.report_date, REPORT_TIMES.get(event.report_time or ""))
    construction = decision.construction or ""
    when = REPORT_WORDS.get(event.report_time or "", "время не подтверждено")
    risk_usd = thresholds.capital.module_usd * risk_fraction
    name = NAMES.get(construction, construction)
    account = "PAPER" if card is None or card.paper else "REAL"
    if card is not None and card.paper and card.plan and construction in STOCK_CONSTRUCTIONS:
        return stock_signal_text(event, decision, thresholds, card, exit_reason)
    lines = [f"{event.ticker} · отчёт {_day(event.report_date)} {when} · {name} · {account}"]
    if construction in ("straddle", "iron_condor"):
        straddle, condor = thresholds.constructions.straddle, thresholds.constructions.iron_condor
        exit_rule = (
            f"стоп −{straddle.stop_premium_loss:.0%} премии, "
            f"цель +{straddle.target_premium_gain:.0%}"
            if construction == "straddle"
            else f"стоп {condor.stop_premium_multiple:g}× премии, "
            f"цель {condor.target_premium_share:.0%}"
        )
        lines += [
            f"ВХОД   {_at(days.pre, time(15, 30))}, по закрытию",
            f"ВЫХОД  {_at(days.reaction, time(11, 0))} — не позже; {exit_rule}",
        ]
    else:
        c = thresholds.modes.C
        limit = f"лимит — VWAP первого часа ± {c.max_entry_over_vwap:.1%}, до 11:00 ET"
        trail = f"трейлинг {c.trailing_atr_multiple:g} × ATR({c.atr_period})"
        rest = f"закрытие хуже SMA({c.exit_sma_period}), не дольше {c.max_hold_days} дней"
        lines += [
            f"ВХОД   {_at(days.reaction, time(10, 45))}, {limit}",
            f"ВЫХОД  {trail}, {rest}",
        ]
    if card is not None and not card.paper:
        lines += [f"ОРДЕР  {line}" for line in instructions]
        lines.append("       вход — на день; стоп — после исполнения входа, до отмены (GTC)")
        real_risk = float(card.risk_usd or 0)
        lines.append(f"РИСК   ${real_risk:,.0f} (счёт Real)".replace(",", " "))
    else:
        lines.append(f"РИСК   {risk_fraction:.1%} капитала — ${risk_usd:,.0f}".replace(",", " "))
    if card is not None:
        lines.append(f"СТАТУС {status_line(card, exit_reason)}")
    return "\n".join(lines)


def stock_signal_text(
    event: orm.Event,
    decision: orm.Decision,
    thresholds: Thresholds,
    card: orm.TradeCard,
    exit_reason: str | None = None,
) -> str:
    """Сигнал paper-акции режима C: цена, количество, стоп, выход — для ручного исполнения.

    Целей (TP) у режима C нет, вероятностей касания и R:R система не считает — их в тексте нет.
    """
    plan = CardPlan.model_validate(card.plan, strict=False)
    c = thresholds.modes.C
    is_long = decision.construction == "stock"
    when = REPORT_WORDS.get(event.report_time or "", "время не подтверждено")
    until = plan.entry_until or time(11, 0)
    deadline = datetime.combine(
        reaction_day(event.report_date, REPORT_TIMES.get(event.report_time or "")), until, tzinfo=ET
    )
    stop_pct = (plan.stop_price - plan.limit_price) / plan.limit_price
    trail = f"{c.trailing_atr_multiple:g} × ATR({c.atr_period})"
    head = f"#{card.id} {'🟢' if is_long else '🔴'} {event.ticker}"
    limit_rule = f"лимит: VWAP первого часа ± {c.max_entry_over_vwap:.1%}"
    limit_until = f"до {until:%H:%M} ET / {deadline.astimezone(MSK):%H:%M} МСК"
    position = f"{plan.shares} целых акций, {_usd(plan.shares * plan.limit_price)}"
    risk = f"{_usd(plan.risk_usd)} ({plan.risk_usd / thresholds.capital.module_usd:.1%} капитала)"
    exit_rule = f"трейлинг {trail} после закрытия · закрытие хуже SMA({c.exit_sma_period})"
    lines = [
        f"{head} · {'ЛОНГ' if is_long else 'ШОРТ'}",
        "",
        "📡 PAPER-сигнал · ручное исполнение",
        "Цена сигнала — лимит эмуляции, не брокерский fill; проверь цену перед заявкой.",
        "",
        f"📅 Отчёт {_day(event.report_date)} {when}",
        f"⏱ Сигнал: {_moment(decision.decided_at)}",
        f"💵 Цена сигнала:  {_usd(plan.limit_price)}  ({limit_rule}, {limit_until})",
        f"📦 План: {position} · риск {risk}",
        f"🛑 Стоп:  {_usd(plan.stop_price)}  ({_pct(stop_pct)}) · стартовый, {trail}",
        f"🚪 Выход: {exit_rule} · не дольше {c.max_hold_days} дн.",
        "🎯 Фиксированных целей (TP) нет: позицию ведёт трейлинг-стоп.",
        "",
        f"СТАТУС {_stock_status(card, until, exit_reason)}",
    ]
    return "\n".join(lines)


def closed_text(
    event: orm.Event, decision: orm.Decision, card: orm.TradeCard, exit_reason: str | None
) -> str | None:
    """«СИГНАЛ ЗАКРЫТ» paper-акции: цена закрытия, итог, что сделать у брокера; нет входа — None."""
    entries = _fills(card, "entry")
    exits = _fills(card, "stop", "exit")
    if not entries or not exits:
        return None
    entry, out = entries[0], exits[-1]
    sign = 1 if decision.construction == "stock" else -1
    result = sign * (out.price - entry.price) / entry.price
    reason = STOP_REASONS.get(exit_reason or "", exit_reason or "")
    lines = [
        f"#{card.id} 🔵 {event.ticker} · СИГНАЛ ЗАКРЫТ · {reason}",
        "",
        f"🏁 Цена закрытия позиции: {_usd(out.price)} ({_pct(result)}).",
        f"💵 Цена входа: {_usd(entry.price)} · {_moment(entry.at)} · {entry.quantity:g} акц.",
    ]
    if card.pnl_total is not None:
        pnl = float(card.pnl_total)
        lines.append(f"📊 Итог paper: {'+' if pnl >= 0 else '−'}{_usd(abs(pnl))}")
    if exit_reason in ("sma", "max_hold"):
        lines.append(
            f"Условие выхода выполнено по закрытию {out.at:%d.%m} — закрой на следующем открытии."
        )
    elif exit_reason in ("trail_stop", "stop"):
        lines.append(f"Стоп сработал {out.at:%d.%m}.")
    lines += ["", "Если позиция открыта: сверь текущую цену и закрой оставшуюся позицию у брокера."]
    return "\n".join(lines)


def _stock_status(card: orm.TradeCard, until: time, exit_reason: str | None) -> str:
    entry = next(iter(_fills(card, "entry")), None)
    if card.state == "PLANNED":
        return (
            f"ждём исполнения лимита до {until:%H:%M} ET — "
            "эмуляция проверяет бары, сообщение обновится"
        )
    if card.state in ("ARMED", "OPEN", "C_MODE", "CLOSING"):
        if entry is None:
            return "вход исполняется"
        stop = (card.trailing or {}).get("stop") or (card.stop or {}).get("price")
        return (
            f"✅ вход исполнен {_moment(entry.at)} по {_usd(entry.price)} · {entry.quantity:g} акц."
            + (f" · стоп {_usd(stop)}" if stop else "")
        )
    if card.state in ("CLOSED", "STOPPED"):
        return status_line(card, exit_reason)
    return f"⛔ вход не исполнен: {exit_reason or 'отменён'} — позицию не открываем"


def _fills(card: orm.TradeCard, *purposes: str) -> list[CardFill]:
    return [
        CardFill.model_validate(f, strict=False)
        for f in card.fills or []
        if f.get("purpose") in purposes
    ]


def _moment(value: datetime) -> str:
    return (
        f"{_day(to_et(value).date())} {to_et(value):%H:%M} ET ({value.astimezone(MSK):%H:%M} МСК)"
    )


def _usd(value: float) -> str:
    return f"${value:,.2f}".replace(",", " ")


def _pct(value: float) -> str:
    return f"{value:+.1%}".replace(".", ",").replace("-", "−")


def status_line(card: orm.TradeCard, exit_reason: str | None = None) -> str:
    """Состояние карточки словами — строка, которую правит смена состояния."""
    if card.state == "PLANNED":
        return "ждём вход"
    if card.state == "ARMED" and not card.paper:
        return "ордера выставлены — ждём исполнения у брокера"
    if card.state in ("ARMED", "OPEN", "C_MODE", "CLOSING"):
        trailing = (card.trailing or {}).get("stop")
        return "открыта" + (f" · стоп {trailing:.2f}" if trailing is not None else "")
    if card.state in ("CLOSED", "STOPPED"):
        reason = STOP_REASONS.get(exit_reason or "", "")
        pnl = float(card.pnl_total) if card.pnl_total is not None else None
        result = (
            ""
            if pnl is None
            else f" · итог {'+' if pnl >= 0 else '−'}${abs(pnl):,.0f}".replace(",", " ")
        )
        return f"закрыта{f' ({reason})' if reason else ''}{result}"
    return f"отменена: {exit_reason}" if exit_reason else "отменена"


def send_new_signals(session: Session, client: Sender, thresholds: Thresholds) -> int:
    """Новые входы (Paper и Real) — сообщением с кнопками; при смене состояния — правка."""
    rows = session.execute(
        select(orm.TradeCard, orm.Decision, orm.Event)
        .join(orm.Decision, orm.Decision.id == orm.TradeCard.decision_id)
        .join(orm.Event, orm.Event.id == orm.Decision.event_id)
        .where(
            (
                orm.TradeCard.tg_message_id.is_(None)
                & orm.TradeCard.state.in_(("PLANNED", "ARMED", "OPEN"))
            )
            | (
                orm.TradeCard.tg_message_id.is_not(None)
                & (orm.TradeCard.tg_state.is_distinct_from(orm.TradeCard.state))
            )
        )
        .order_by(orm.TradeCard.id)
    ).all()
    done = 0
    for card, decision, event in rows:
        reason = session.scalars(
            select(orm.TradeCardTransition.reason)
            .where(orm.TradeCardTransition.card_id == card.id)
            .order_by(orm.TradeCardTransition.id.desc())
            .limit(1)
        ).first()
        instructions = (
            []
            if card.paper
            else session.scalars(
                select(orm.BrokerOrder.instruction)
                .where(orm.BrokerOrder.card_id == card.id)
                .order_by(orm.BrokerOrder.created_at, orm.BrokerOrder.client_order_id)
            ).all()
        )
        text = signal_text(
            event, decision, _risk(session, decision), thresholds, card, reason, instructions
        )
        buttons = card_buttons(card)
        if card.tg_message_id is None:
            card.tg_message_id = client.send(text, buttons=buttons)
        else:
            client.edit(card.tg_message_id, text, buttons=buttons)
        if (
            card.paper
            and card.state in ("CLOSED", "STOPPED")
            and decision.construction in STOCK_CONSTRUCTIONS
        ):  # отдельное сообщение со звуком: позицию нужно закрыть у брокера
            closing = closed_text(event, decision, card, reason)
            if closing is not None:
                client.send(closing)
        card.tg_state = card.state
        session.commit()  # отправленное фиксируется сразу: сбой на следующей его не повторит
        done += 1
    return done


def skip_text(session: Session, event: orm.Event, decision: orm.Decision) -> str:
    """«ПРОПУСК» (SPEC §12): главная причина, остальные — «Доп.», теневая сделка."""
    when = REPORT_WORDS.get(event.report_time or "", "время не подтверждено")
    reasons = list(decision.reasons or [])
    lines = [f"{event.ticker} · отчёт {_day(event.report_date)} {when} · НЕ ВХОДИМ"]
    if reasons:
        lines.append(f"Причина: {reasons[0]} — {REASON_WORDS.get(reasons[0], reasons[0])}")
        lines += [f"Доп.: {r} — {REASON_WORDS.get(r, r)}" for r in reasons[1:]]
    rejected = session.scalar(
        select(orm.DecisionStep.id)
        .where(
            orm.DecisionStep.event_id == event.id,
            orm.DecisionStep.construction.is_not(None),
            orm.DecisionStep.is_shadow.is_(False),
        )
        .limit(1)
    )
    if rejected is not None:
        lines.append("Теневая сделка — посчитается вечером после реакции")
    return "\n".join(lines)


def send_skips(session: Session, client: Sender) -> int:
    """«ПРОПУСК» по новым итогам SKIPPED — без звука, один раз."""
    rows = session.execute(
        select(orm.Decision, orm.Event)
        .join(orm.Event, orm.Event.id == orm.Decision.event_id)
        .where(orm.Decision.status == "SKIPPED", orm.Decision.tg_message_id.is_(None))
        .order_by(orm.Decision.id)
    ).all()
    for decision, event in rows:
        decision.tg_message_id = client.send(skip_text(session, event, decision), silent=True)
        session.commit()
    return len(rows)


def escort_text(session: Session, now: datetime) -> str | None:
    """«СОПРОВОЖДЕНИЕ» (SPEC §12): открытые paper-позиции и их стопы после пересчёта; нет — None."""
    rows = session.execute(
        select(orm.TradeCard, orm.Decision, orm.Event)
        .join(orm.Decision, orm.Decision.id == orm.TradeCard.decision_id)
        .join(orm.Event, orm.Event.id == orm.Decision.event_id)
        .where(orm.TradeCard.paper.is_(True), orm.TradeCard.state.in_(("OPEN", "C_MODE")))
        .order_by(orm.TradeCard.id)
    ).all()
    if not rows:
        return None
    et = to_et(now)
    lines = [f"СОПРОВОЖДЕНИЕ · {et:%d.%m} {et:%H:%M} ET ({now.astimezone(MSK):%H:%M} МСК)"]
    for card, decision, event in rows:
        name = NAMES.get(decision.construction or "", decision.construction or "")
        stop = (card.trailing or {}).get("stop")
        rule = (card.stop or {}).get("rule", "")
        lines.append(
            f"{event.ticker} · {name} · " + (f"стоп {stop:.2f}" if stop is not None else rule)
        )
    return "\n".join(lines)


def _risk(session: Session, decision: orm.Decision) -> float:
    found = session.scalars(
        select(orm.DecisionStep.risk_fraction)
        .where(
            orm.DecisionStep.event_id == decision.event_id,
            orm.DecisionStep.strategy_id == decision.strategy_id,
            orm.DecisionStep.outcome == "proposal",
        )
        .order_by(orm.DecisionStep.id.desc())
        .limit(1)
    ).first()
    return found or 0.0


def _at(day: date, clock: time) -> str:
    moment = datetime.combine(day, clock, tzinfo=ET)
    return f"{_day(day)} {to_et(moment):%H:%M} ET ({moment.astimezone(MSK):%H:%M} МСК)"


def _day(value: date) -> str:
    return f"{value:%d.%m}"
