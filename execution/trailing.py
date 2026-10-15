"""Трейлинг-стоп открытых сделок режима C (SPEC §10, T17): пересчёт после закрытия, 16:20 ET;
затем «СОПРОВОЖДЕНИЕ» в Telegram — открытые позиции и стопы (SPEC §12).

Стоп = закрытие ∓ 2 × ATR(14), только в сторону сделки — те же правила, что в бэктесте
(`backtest.mode_c.trailing_now`). Пишется в карточку (`trailing`); выход по стопу ведёт вечерний
прогон paper-сделок.
"""

import logging
import statistics
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.cache import RedisCache
from adapters.massive.client import MassiveClient, massive_api_key
from adapters.massive.models import Bar
from adapters.massive.symbols import StockHistorySource, daily_bars
from backtest.mode_c import Entry, trailing_now
from core.config import AppConfig, load_config
from core.config.thresholds import ModeC, Thresholds
from core.db import models as orm
from core.domain.trading import CardFill, CardTrailing
from core.error_log import logged_job
from core.scheduler.jobs import engine
from core.session_guard import is_trading_day, to_et
from notify.signals import escort_text
from notify.telegram.client import TelegramClient

logger = logging.getLogger(__name__)

HISTORY_DAYS = 60  # дневные свечи до входа: ATR(14)


def update_trailing(
    session: Session,
    stocks: StockHistorySource,
    thresholds: Thresholds,
    now: datetime,
    notes: list[str] | None = None,
) -> int:
    """Пересчитать стоп открытых карточек режима C; вернуть число обновлённых.

    notes — строки для Real (E10-3): новый уровень стопа, который человек переставляет у брокера,
    и сигнал выхода по правилам бэктеста (закрытие хуже SMA, срок удержания).
    """
    rules = thresholds.modes.C
    rows = session.execute(
        select(orm.TradeCard, orm.Event)
        .join(orm.Decision, orm.Decision.id == orm.TradeCard.decision_id)
        .join(orm.Event, orm.Event.id == orm.Decision.event_id)
        .where(orm.Decision.mode == "C", orm.TradeCard.state == "OPEN")
        .order_by(orm.TradeCard.id)
    ).all()
    updated = 0
    for card, event in rows:
        entry = next(
            (
                CardFill.model_validate(f, strict=False)
                for f in card.fills or []
                if f.get("purpose") == "entry"
            ),
            None,
        )
        if entry is None:
            continue
        entry_day = to_et(entry.at).date()
        position = Entry(1 if entry.side == "buy" else -1, entry.price, entry.at)
        today = to_et(now).date()
        bars = daily_bars(stocks, event.ticker, entry_day - timedelta(days=HISTORY_DAYS), today)
        state = trailing_now(position, bars, entry_day, rules)
        if state is None:
            logger.warning("no trailing stop", extra={"card_id": card.id, "ticker": event.ticker})
            continue
        stop, atr = state
        previous = (card.trailing or {}).get("stop") or (card.stop or {}).get("price")
        if notes is not None and not card.paper:
            notes += _real_notes(
                card, event.ticker, previous, stop, position, bars, entry_day, rules
            )
        card.trailing = CardTrailing(
            atr=atr, multiple=rules.trailing_atr_multiple, stop=stop, updated_at=now
        ).model_dump(mode="json")
        updated += 1
    return updated


def _real_notes(
    card: orm.TradeCard,
    ticker: str,
    previous: float | None,
    stop: float,
    position: Entry,
    bars: Sequence[Bar],
    entry_day: date,
    rules: ModeC,
) -> list[str]:
    head = f"REAL {ticker} #{card.id}"
    out = []
    if previous is None or abs(stop - float(previous)) >= 0.01:
        was = f" (было {float(previous):.2f})" if previous is not None else ""
        out.append(f"{head}: переставьте стоп на {stop:.2f}{was}")
    after = [b for b in bars if to_et(b.start).date() >= entry_day]
    closes = [b.close for b in bars][-rules.exit_sma_period :]
    if after and len(closes) == rules.exit_sma_period:
        last = after[-1].close
        if position.direction * (last - statistics.fmean(closes)) < 0:
            out.append(f"{head}: закройте на открытии — закрытие хуже SMA({rules.exit_sma_period})")
        elif len(after) - 1 >= rules.max_hold_days:
            out.append(f"{head}: закройте на открытии — срок {rules.max_hold_days} дней вышел")
    return out


def build_stocks(config: AppConfig) -> StockHistorySource:  # pragma: no cover
    """Massive с кэшем Redis."""
    cache = RedisCache.from_env(config.sources.redis.timeout_seconds)
    return MassiveClient.create(config.sources.massive, massive_api_key(), cache)


@logged_job("trailing-daily", lambda: engine())
def run_trailing_update(
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    stocks_factory: Callable[[AppConfig], StockHistorySource] = build_stocks,
) -> int | None:
    """Задача планировщика; в неторговый день ничего не делает."""
    moment = now()
    if not is_trading_day(to_et(moment).date()):
        return None
    config = load_config()
    stocks = stocks_factory(config)
    notes: list[str] = []
    with Session(engine()) as session, session.begin():
        updated = update_trailing(session, stocks, config.thresholds, moment, notes)
        text = escort_text(session, moment)
    client = TelegramClient.from_env()
    if client is not None and text is not None:
        client.send(text, silent=True)  # СОПРОВОЖДЕНИЕ (SPEC §12) — после пересчёта стопов
    if client is not None and notes:  # Real — со звуком: действие у брокера
        client.send("СОПРОВОЖДЕНИЕ · REAL\n" + "\n".join(notes))
    return updated
