"""Эмуляция входа paper режима C по минутным барам и новый вид сигнала (карточка #id)."""

import math
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.massive.models import Bar, TickerChange
from backtest.simulate import LegFill, Trade
from core.config import load_config
from core.db import models as orm
from core.db.store import sync_universe
from core.domain.trading import CardFill
from core.session_guard import ET, previous_trading_day
from execution.cards import open_card, stock_plan_of
from execution.paper import PaperBook
from execution.paper_fill import fill_planned_cards
from learning.shadow import Shadow
from notify.signals import closed_text, send_new_signals, signal_text
from strategies.mode_c.strategy import stock_plan

CONFIG = load_config()
THRESHOLDS = CONFIG.thresholds
REACTION = date(2025, 10, 22)  # BMO: накануне — 21.10
DECIDED = datetime(2025, 10, 22, 14, 45, 31, tzinfo=UTC)  # 10:45:31 ET = 17:45 МСК
NOW = datetime(2025, 10, 22, 14, 50, tzinfo=UTC)  # 10:50 ET: окно лимита ещё открыто
VWAP = (105 * 3000 + 106 * 100) / 3100  # VWAP первого часа; лимит = VWAP × 1,003
LIMIT = VWAP * 1.003


def bar(day: date, hh: int, mm: int, close: float, volume: float, **kw: float) -> Bar:
    start = datetime.combine(day, time(hh, mm), tzinfo=ET)
    return Bar.model_validate(
        {
            "o": kw.get("open", close),
            "h": kw.get("high", close),
            "l": kw.get("low", close),
            "c": close,
            "v": volume,
            "vw": kw.get("vwap", close),
            "t": start.timestamp() * 1000,
        }
    )


def days_before(day: date, count: int) -> list[date]:
    out = []
    for _ in range(count):
        day = previous_trading_day(day)
        out.append(day)
    return list(reversed(out))


class Stocks:
    """Плоская история (ATR 2,0, закрытие накануне 100); минуты дня реакции — по сценарию."""

    def __init__(self, low_1031: float = 105.0, late_bar: bool = False) -> None:
        self.low_1031 = low_1031  # ниже лимита 105,35 — лимит исполняется в 10:31
        self.late_bar = late_bar  # бар не раньше 11:00 — окно лимита закрыто в данных

    def ticker_changes(self, ticker: str) -> list[TickerChange]:
        return []

    def aggregates(
        self, ticker: str, multiplier: int, timespan: str, start: date, end: date, **kwargs: Any
    ) -> list[Bar]:
        if timespan == "minute":
            past = [bar(d, 9, 31, 100, 1000) for d in days_before(REACTION, 20)]
            first_hour = [
                bar(REACTION, 9, 31, 105, 3000, vwap=105),
                bar(REACTION, 10, 29, 106, 100),
            ]
            entry = bar(REACTION, 10, 31, 106, 100, low=self.low_1031, high=107)
            late = [bar(REACTION, 11, 1, 106, 100)] if self.late_bar else []
            return [*past, *first_hour, entry, *late]
        return [bar(d, 0, 0, 100, 1e6, high=101, low=99) for d in days_before(REACTION, 60)]


def planned_card(
    session: Session, *, with_plan: bool = True
) -> tuple[orm.Event, orm.Decision, orm.TradeCard]:
    sync_universe(session, CONFIG.universe)
    event = orm.Event(
        ticker="NFLX", report_date=REACTION, report_time="BMO", date_status="confirmed"
    )
    session.add(event)
    session.flush()
    decision = orm.Decision(
        event_id=event.id,
        status="ENTERED",
        reasons=[],
        mode="C",
        strategy_id="mode_c",
        construction="stock",
        decided_at=DECIDED,
    )
    session.add(decision)
    session.add(
        orm.DecisionStep(
            event_id=event.id,
            stage="T0",
            job="mode_c_decision",
            strategy_id="mode_c",
            is_shadow=False,
            outcome="proposal",
            mode="C",
            construction="stock",
            reasons=[],
            risk_fraction=0.01,
            at=DECIDED,
        )
    )
    session.flush()
    plan = stock_plan_of(stock_plan("NFLX", 1, round(LIMIT, 2), 4.0, 0.0005), 1000.0)
    return event, decision, open_card(session, decision, plan if with_plan else None)


def last_reason(session: Session, card: orm.TradeCard) -> str | None:
    return session.scalars(
        select(orm.TradeCardTransition.reason)
        .where(orm.TradeCardTransition.card_id == card.id)
        .order_by(orm.TradeCardTransition.id.desc())
        .limit(1)
    ).first()


def test_filled_entry_takes_price_and_time_from_the_bar(session: Session) -> None:
    _, _, card = planned_card(session)
    result = fill_planned_cards(session, Stocks(), THRESHOLDS, NOW, closed_after=time(16, 30))
    assert (result.opened, result.cancelled, result.pending) == (1, 0, 0)
    assert card.state == "OPEN"
    assert card.fills is not None
    assert card.stop is not None
    [fill] = card.fills
    assert fill["price"] == pytest.approx(LIMIT)
    assert datetime.fromisoformat(fill["at"]) == datetime(2025, 10, 22, 10, 31, tzinfo=ET)
    shares = math.floor(1000 / (2 * 2.0))  # целые акции под риск 1% при стопе 2×ATR
    assert fill["quantity"] == shares
    assert [leg["quantity"] for leg in card.legs] == [250]
    assert card.stop["price"] == pytest.approx(LIMIT - 4.0)  # стартовый стоп — от цены исполнения


def test_entry_is_not_cancelled_while_the_limit_window_is_open(session: Session) -> None:
    _, _, card = planned_card(session)
    stocks = Stocks(low_1031=105.4)  # лимит 105,35 не достигнут, баров после 11:00 ещё нет
    result = fill_planned_cards(session, stocks, THRESHOLDS, NOW, closed_after=time(16, 30))
    assert (result.opened, result.cancelled, result.pending) == (0, 0, 1)
    assert card.state == "PLANNED"


def test_entry_is_cancelled_when_data_shows_the_window_is_closed(session: Session) -> None:
    _, _, card = planned_card(session)
    stocks = Stocks(low_1031=105.4, late_bar=True)  # есть бар 11:01 — окно лимита закрыто
    result = fill_planned_cards(session, stocks, THRESHOLDS, NOW, closed_after=time(16, 30))
    assert (result.opened, result.cancelled) == (0, 1)
    assert card.state == "CANCELLED"
    assert last_reason(session, card) == f"лимит {LIMIT:.2f} не достигнут до 11:00 ET"


def test_entry_is_cancelled_once_the_day_is_published(session: Session) -> None:
    _, _, card = planned_card(session)
    evening = datetime(2025, 10, 22, 20, 45, tzinfo=UTC)  # 16:45 ET, после closed_after
    fill_planned_cards(
        session, Stocks(low_1031=105.4), THRESHOLDS, evening, closed_after=time(16, 30)
    )
    assert card.state == "CANCELLED"


def test_card_for_a_future_reaction_waits(session: Session) -> None:
    _, _, card = planned_card(session)
    day_before = datetime(2025, 10, 21, 20, 0, tzinfo=UTC)
    result = fill_planned_cards(
        session, Stocks(), THRESHOLDS, day_before, closed_after=time(16, 30)
    )
    assert result.pending == 1
    assert card.state == "PLANNED"


def test_card_without_a_saved_plan_gets_one_when_filled(session: Session) -> None:
    _, _, card = planned_card(session, with_plan=False)
    assert card.plan is None
    fill_planned_cards(session, Stocks(), THRESHOLDS, NOW, closed_after=time(16, 30))
    assert card.plan is not None
    assert card.plan["shares"] == 250
    assert card.plan["limit_price"] == pytest.approx(LIMIT)


def test_signal_text_for_a_planned_card(session: Session) -> None:
    event, decision, card = planned_card(session)
    text = signal_text(event, decision, 0.01, THRESHOLDS, card)
    assert f"#{card.id} 🟢 NFLX · ЛОНГ" in text
    assert "📡 PAPER-сигнал · ручное исполнение" in text
    assert "⏱ Сигнал: 22.10 10:45 ET (17:45 МСК)" in text  # время решения — фактическое
    assert "до 11:00 ET / 18:00 МСК" in text
    assert "📦 План: 250 целых акций, $26 337.50 · риск $1 000.00 (1.0% капитала)" in text
    assert "🛑 Стоп:  $101.35  (−3,8%)" in text
    assert "Фиксированных целей (TP) нет" in text
    assert "СТАТУС ждём исполнения лимита до 11:00 ET" in text


def test_signal_text_shows_the_actual_fill_after_entry(session: Session) -> None:
    event, decision, card = planned_card(session)
    fill_planned_cards(session, Stocks(), THRESHOLDS, NOW, closed_after=time(16, 30))
    text = signal_text(event, decision, 0.01, THRESHOLDS, card, last_reason(session, card))
    assert "СТАТУС ✅ вход исполнен 22.10 10:31 ET (17:31 МСК) по $105.35 · 250 акц." in text
    assert "стоп $101.35" in text


def test_signal_text_for_a_cancelled_entry(session: Session) -> None:
    event, decision, card = planned_card(session)
    fill_planned_cards(
        session, Stocks(low_1031=105.4, late_bar=True), THRESHOLDS, NOW, closed_after=time(16, 30)
    )
    text = signal_text(event, decision, 0.01, THRESHOLDS, card, last_reason(session, card))
    assert "СТАТУС ⛔ вход не исполнен: лимит" in text
    assert "позицию не открываем" in text


def stopped(session: Session, card: orm.TradeCard) -> None:
    exit_fill = CardFill(
        symbol="NFLX",
        side="sell",
        quantity=250,
        price=101.35,
        at=datetime(2025, 10, 23, 9, 30, tzinfo=ET),
        purpose="stop",
    )
    card.fills = [*(card.fills or []), exit_fill.model_dump(mode="json")]
    card.pnl_total = Decimal("-920.00")
    card.state = "STOPPED"


def test_closed_text_tells_what_to_do_at_the_broker(session: Session) -> None:
    event, decision, card = planned_card(session)
    fill_planned_cards(session, Stocks(), THRESHOLDS, NOW, closed_after=time(16, 30))
    stopped(session, card)
    text = closed_text(event, decision, card, "trail_stop")
    assert text is not None
    assert text.splitlines()[0] == f"#{card.id} 🔵 NFLX · СИГНАЛ ЗАКРЫТ · трейлинг-стоп"
    assert "🏁 Цена закрытия позиции: $101.35 (−3,8%)." in text
    assert "💵 Цена входа: $105.35 · 22.10 10:31 ET (17:31 МСК) · 250 акц." in text
    assert "📊 Итог paper: −$920.00" in text
    assert "Стоп сработал 23.10." in text
    assert text.endswith("закрой оставшуюся позицию у брокера.")


def test_closed_text_for_an_sma_exit_asks_to_close_at_the_next_open(session: Session) -> None:
    event, decision, card = planned_card(session)
    fill_planned_cards(session, Stocks(), THRESHOLDS, NOW, closed_after=time(16, 30))
    stopped(session, card)
    text = closed_text(event, decision, card, "sma")
    assert text is not None
    assert "закрой на следующем открытии" in text


def test_closed_text_needs_an_entry(session: Session) -> None:
    event, decision, card = planned_card(session)
    assert closed_text(event, decision, card, "sma") is None  # входа не было — закрывать нечего


class Calculator:
    def __init__(self, outcome: Shadow) -> None:
        self.outcome = outcome

    def evaluate(
        self, session: Session, step: orm.DecisionStep, event: orm.Event, days: Any, today: date
    ) -> Shadow:
        return self.outcome


def test_evening_run_keeps_the_filled_entry_and_exits_with_the_same_shares(
    session: Session,
) -> None:
    _, _, card = planned_card(session)
    fill_planned_cards(session, Stocks(), THRESHOLDS, NOW, closed_after=time(16, 30))
    closed = Trade(
        ticker="NFLX",
        report_date=REACTION,
        construction="mode_c",
        entry_value=LIMIT,
        exit_value=101.35,
        exit_reason="trail_stop",
        exit_at=datetime(2025, 10, 23, 9, 30, tzinfo=ET),
        gross_pnl=-999.0,
        costs=5.0,
        risk=1005.0,
        variant="long",
        entry_on=REACTION,
        entry_at=datetime(2025, 10, 22, 10, 31, tzinfo=ET),
        legs=(LegFill("NFLX", "stock", 1, 250, 1, LIMIT, 101.35),),
    )
    result = PaperBook(Calculator(Shadow("closed", trade=closed)), THRESHOLDS).run(
        session, date(2025, 10, 23), date(2025, 10, 16)
    )
    assert result.counts == {"STOPPED": 1}
    assert card.fills is not None
    entry, exit_ = card.fills
    assert (entry["purpose"], entry["quantity"], entry["price"]) == (
        "entry",
        250,
        pytest.approx(LIMIT),
    )
    assert datetime.fromisoformat(entry["at"]) == datetime(2025, 10, 22, 10, 31, tzinfo=ET)
    assert (exit_["purpose"], exit_["quantity"]) == ("stop", 250)  # те же целые акции, не доля
    moves = session.scalars(select(orm.TradeCardTransition).order_by(orm.TradeCardTransition.id))
    assert [(m.from_state, m.to_state) for m in moves] == [
        (None, "PLANNED"),
        ("PLANNED", "ARMED"),
        ("ARMED", "OPEN"),
        ("OPEN", "STOPPED"),  # вход не проводится второй раз
    ]


class Bot:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.edited: list[str] = []

    def send(
        self,
        text: str,
        *,
        silent: bool = False,
        buttons: list[tuple[str, str]] | None = None,
        reply_to: int | None = None,
    ) -> int:
        self.sent.append(text)
        return 100 + len(self.sent)

    def edit(
        self, message_id: int, text: str, *, buttons: list[tuple[str, str]] | None = None
    ) -> None:
        self.edited.append(text)


def test_closing_sends_a_separate_message_and_edits_the_card(session: Session) -> None:
    _, _, card = planned_card(session)
    bot = Bot()
    assert send_new_signals(session, bot, THRESHOLDS) == 1  # PLANNED: первое сообщение
    assert len(bot.sent) == 1
    assert "СТАТУС ждём исполнения лимита" in bot.sent[0]
    fill_planned_cards(session, Stocks(), THRESHOLDS, NOW, closed_after=time(16, 30))
    assert send_new_signals(session, bot, THRESHOLDS) == 1  # OPEN: правка той же карточки
    assert len(bot.sent) == 1
    assert "✅ вход исполнен" in bot.edited[-1]
    stopped(session, card)
    assert send_new_signals(session, bot, THRESHOLDS) == 1  # STOPPED: правка и отдельное сообщение
    assert len(bot.sent) == 2
    assert "СИГНАЛ ЗАКРЫТ" in bot.sent[1]
    assert send_new_signals(session, bot, THRESHOLDS) == 0  # повтор ничего не шлёт


def test_stock_plan_of_sizes_whole_shares_for_a_short() -> None:
    plan = stock_plan_of(stock_plan("NFLX", -1, 100.0, 2.5, 0.001), 1000.0)
    assert plan is not None
    assert (plan.limit_price, plan.stop_price, plan.stop_distance) == (100.0, 102.5, 2.5)
    assert plan.shares == 400  # floor(1000 / 2,5)
    assert stock_plan_of(None, 1000.0) is None
    assert stock_plan_of(stock_plan("NFLX", 1, 100.0, 2.5, 0.001), 0.0) is None
