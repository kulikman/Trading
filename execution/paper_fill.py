"""Эмуляция входа paper-сделок режима C по минутным барам: исполнился ли лимит и когда.

Раньше вход paper считал только вечерний прогон архива, а карточка оставалась PLANNED до выхода.
Теперь задача `paper-fill` (пн–пт, каждые несколько минут в окне ET из schedule.yaml) берёт
PLANNED-карточки режима C и по тем же правилам, что бэктест (`backtest.mode_c.entry`), смотрит
минутные бары дня реакции:
- лимит достигнут — карточка PLANNED → ARMED → OPEN; цена и минута исполнения — из бара, а не
  номинальное время решения;
- окно лимита закрыто (в данных есть бар не раньше fill_deadline_et или день закончился), а входа
  нет — CANCELLED с причиной;
- иначе данных для вывода ещё нет — карточка ждёт следующего запуска.
Сообщение в Telegram правится само при смене состояния (notify.signals.send_new_signals).
"""

import logging
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Literal, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.cache import RedisCache
from adapters.massive.client import MassiveClient, massive_api_key
from adapters.massive.models import Bar, TickerChange
from adapters.massive.symbols import StockHistorySource, symbol_on, symbol_periods
from backtest.mode_c import Entry, confirm, entry, entry_limit
from backtest.mode_c_run import previous_days
from core.config import AppConfig, load_config
from core.config.thresholds import Thresholds
from core.db import models as orm
from core.domain.broker import Side
from core.domain.trading import CardFill, CardLeg, CardPlan, CardStop
from core.error_log import logged_job
from core.registry.agent_jobs import REPORT_TIMES
from core.scheduler.jobs import engine
from core.session_guard import ET, is_trading_day, reaction_day, to_et
from core.state_machine.card import transition
from execution.paper import entry_step
from strategies.common import stock_state

logger = logging.getLogger(__name__)


class StockData(StockHistorySource, Protocol):
    def aggregates(
        self,
        ticker: str,
        multiplier: int,
        timespan: Literal["day", "minute"],
        start: date,
        end: date,
        *,
        adjusted: bool = True,
    ) -> list[Bar]:
        """Свечи."""

    def ticker_changes(self, ticker: str) -> list[TickerChange]:
        """История тикеров."""


@dataclass
class FillResult:
    opened: int = 0
    cancelled: int = 0
    pending: int = 0


def fill_planned_cards(
    session: Session,
    stocks: StockData,
    thresholds: Thresholds,
    now: datetime,
    *,
    closed_after: time,
) -> FillResult:
    """Провести PLANNED-карточки режима C: вход по барам или отмена, если окно лимита закрыто.

    closed_after — время ET, после которого день реакции считается полностью опубликованным
    (бар после fill_deadline_et может и не появиться у малоторгуемой акции).
    """
    result = FillResult()
    today = to_et(now).date()
    rows = session.execute(
        select(orm.TradeCard, orm.Decision, orm.Event)
        .join(orm.Decision, orm.Decision.id == orm.TradeCard.decision_id)
        .join(orm.Event, orm.Event.id == orm.Decision.event_id)
        .where(
            orm.TradeCard.paper.is_(True),
            orm.TradeCard.state == "PLANNED",
            orm.Decision.mode == "C",
        )
        .order_by(orm.TradeCard.id)
    ).all()
    for card, decision, event in rows:
        reaction = reaction_day(event.report_date, REPORT_TIMES.get(event.report_time or ""))
        if reaction > today:
            result.pending += 1
            continue
        outcome = _fill_one(session, stocks, thresholds, now, closed_after, card, decision, event)
        setattr(result, outcome, getattr(result, outcome) + 1)
    return result


def _fill_one(
    session: Session,
    stocks: StockData,
    thresholds: Thresholds,
    now: datetime,
    closed_after: time,
    card: orm.TradeCard,
    decision: orm.Decision,
    event: orm.Event,
) -> Literal["opened", "cancelled", "pending"]:
    rules, settings = thresholds.modes.C, thresholds.backtest.mode_c
    reaction = reaction_day(event.report_date, REPORT_TIMES.get(event.report_time or ""))
    direction: Literal[1, -1] = 1 if decision.construction == "stock" else -1
    state = stock_state(stocks, event.ticker, reaction, rules.atr_period)
    if state is None or state.atr is None:
        logger.warning("paper fill: no daily history", extra={"card_id": card.id})
        return "pending"
    history = previous_days(reaction, settings.volume_lookback_days)
    periods = symbol_periods(event.ticker, stocks.ticker_changes(event.ticker))
    minutes = stocks.aggregates(
        symbol_on(periods, reaction), 1, "minute", history[-1], reaction, adjusted=False
    )
    vwap = confirm(direction, state.spot, reaction, minutes, history, rules, settings)
    limit = None if isinstance(vwap, str) else entry_limit(direction, vwap, rules)
    found = entry(direction, state.spot, reaction, minutes, history, rules, settings)
    if isinstance(found, Entry):
        _open(session, card, decision, event, found, limit, state.atr, thresholds)
        return "opened"
    if not _window_closed(minutes, reaction, now, settings.fill_deadline_et, closed_after):
        return "pending"  # данных до конца окна лимита ещё нет — не отменяем по неполным барам
    why = (
        f"лимит {limit:.2f} не достигнут до {settings.fill_deadline_et:%H:%M} ET"
        if found == "not_filled" and limit is not None
        else f"вход не исполнен: {found}"
    )
    at = datetime.combine(reaction, settings.fill_deadline_et, tzinfo=ET)
    transition(session, card, "CANCELLED", at, why, check_session=False)
    logger.info("paper entry not filled", extra={"card_id": card.id, "outcome": str(found)})
    return "cancelled"


def _open(
    session: Session,
    card: orm.TradeCard,
    decision: orm.Decision,
    event: orm.Event,
    found: Entry,
    limit: float | None,
    atr: float,
    thresholds: Thresholds,
) -> None:
    rules, settings = thresholds.modes.C, thresholds.backtest.mode_c
    stop_distance = rules.trailing_atr_multiple * atr
    step = entry_step(session, decision)
    risk_usd = thresholds.capital.module_usd * ((step.risk_fraction or 0.0) if step else 0.0)
    plan = CardPlan.model_validate(card.plan, strict=False) if card.plan else None
    shares = plan.shares if plan else max(1, math.floor(risk_usd / stop_distance))
    stop_price = found.price - found.direction * stop_distance
    side: Side = "buy" if found.direction == 1 else "sell"
    transition(session, card, "ARMED", found.at, "ордер на вход", check_session=False)
    transition(
        session, card, "OPEN", found.at, f"вход исполнен по {found.price:.2f}", check_session=False
    )
    card.legs = [
        CardLeg(
            symbol=event.ticker, instrument="stock", side=side, quantity=shares, multiplier=1
        ).model_dump(mode="json")
    ]
    card.fills = [
        CardFill(
            symbol=event.ticker,
            side=side,
            quantity=shares,
            price=found.price,
            at=found.at,
            purpose="entry",
        ).model_dump(mode="json")
    ]
    card.stop = CardStop(
        rule=f"трейлинг {rules.trailing_atr_multiple:g} × ATR({rules.atr_period}), "
        f"старт {stop_price:.2f}",
        price=stop_price,
    ).model_dump(mode="json")
    if plan is None and risk_usd > 0 and limit is not None:  # карточка до сохранения плана
        card.plan = CardPlan(
            limit_price=limit,
            stop_price=round(limit - found.direction * stop_distance, 2),
            stop_distance=stop_distance,
            shares=shares,
            risk_usd=risk_usd,
            entry_until=settings.fill_deadline_et,
        ).model_dump(mode="json")
    logger.info(
        "paper entry filled",
        extra={"card_id": card.id, "ticker": event.ticker, "price": found.price},
    )


def _window_closed(
    minutes: Sequence[Bar], reaction: date, now: datetime, deadline: time, closed_after: time
) -> bool:
    """Окно лимита закрыто, если в данных есть бар не раньше дедлайна или день уже опубликован."""
    moment = to_et(now)
    if reaction < moment.date():
        return True
    if any(
        to_et(b.start).date() == reaction and to_et(b.start).time() >= deadline for b in minutes
    ):
        return True
    return moment.time() >= closed_after


def build_stocks(config: AppConfig) -> StockData:  # pragma: no cover
    """Massive с кэшем Redis (минутные свечи текущего дня — с коротким TTL)."""
    cache = RedisCache.from_env(config.sources.redis.timeout_seconds)
    return MassiveClient.create(config.sources.massive, massive_api_key(), cache)


@logged_job("paper-fill", lambda: engine())
def run_paper_fill(
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    stocks_factory: Callable[[AppConfig], StockData] = build_stocks,
) -> int | None:
    """Задача планировщика; вне окна и без PLANNED-карточек не обращается к данным."""
    moment = now()
    et = to_et(moment)
    if not is_trading_day(et.date()):
        return None
    config = load_config()
    window = config.schedule.paper_fill
    if not window.from_et <= et.time() <= window.until_et:
        return None
    with Session(engine()) as session, session.begin():
        waiting = session.scalar(
            select(orm.TradeCard.id)
            .join(orm.Decision, orm.Decision.id == orm.TradeCard.decision_id)
            .where(
                orm.TradeCard.paper.is_(True),
                orm.TradeCard.state == "PLANNED",
                orm.Decision.mode == "C",
            )
            .limit(1)
        )
        if waiting is None:
            return 0
        result = fill_planned_cards(
            session,
            stocks_factory(config),
            config.thresholds,
            moment,
            closed_after=window.until_et,
        )
    return result.opened + result.cancelled
