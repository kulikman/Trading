"""«Сделки»: открытые и закрытые, карточка с историей переходов (DASHBOARD.md §4.3).

Открытая сделка: стоимость входа и стоп из карточки (T17); котировок у ручного брокера нет.
"""

from collections.abc import Sequence

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from api.format import Num, count, day, empty, et_msk, money, percent
from api.format import price as price_num
from api.trades_data import ClosedTrade, OpenCard
from core.db import models as orm
from core.session_guard import to_et
from learning.costs import CostCalibration

NO_QUOTES = "котировок нет: ручной брокер"
CALIBRATION = "Калибровка: нет данных до моделей (T15)"


class OpenRow(BaseModel):
    card_id: int
    ticker: str
    mode: str
    state: str
    entry: Num
    price: Num
    pnl: Num
    stop: Num
    next_step: str


class ClosedRow(BaseModel):
    card_id: int
    ticker: str
    dates: str
    mode: str
    result_share: Num
    result: Num
    exit_reason: str


class Trades(BaseModel):
    trust_line: str
    trust_tone: str
    open: list[OpenRow] = []
    closed: list[ClosedRow] = []
    total: str | None = None
    message: str | None = None


class Transition(BaseModel):
    time: str
    change: str
    reason: str


class Card(BaseModel):
    card_id: int
    ticker: str
    mode: str
    state: str
    is_paper: bool
    legs: str
    transitions: list[Transition]


def trust_view(costs: CostCalibration, cost_divergence: float) -> Trades:
    """Строка доверия (DASHBOARD §4.3): красная, если издержки расходятся больше порога."""
    line = f"{CALIBRATION} · Издержки Paper против реальности: {costs.text}"
    over = costs.divergence is not None and abs(costs.divergence) > cost_divergence
    return Trades(trust_line=line, trust_tone="negative" if over else "neutral")


def stop_view(card: OpenCard) -> Num:
    """Стоп открытой сделки: уровень трейлинга, иначе правило стопа словами."""
    if card.stop_price is not None:
        return price_num(card.stop_price)
    return empty(card.stop_rule or "—")


def trades_view(
    state: str,
    open_cards: Sequence[OpenCard],
    closed: Sequence[ClosedTrade],
    capital: float,
    costs: CostCalibration,
    cost_divergence: float,
) -> Trades:
    view = trust_view(costs, cost_divergence)
    if state == "open":
        view.open = [
            OpenRow(
                card_id=c.card_id,
                ticker=c.ticker,
                mode=c.mode or "—",
                state=c.state,
                entry=money(c.entry_value) if c.entry_value is not None else empty("нет входа"),
                price=empty(NO_QUOTES),
                pnl=empty(NO_QUOTES),
                stop=price_num(c.stop_price)
                if c.stop_price is not None
                else empty(c.stop_rule or "—"),
                next_step="—",
            )
            for c in open_cards
        ]
        view.message = None if view.open else "нет открытых сделок"
        return view
    view.closed = [
        ClosedRow(
            card_id=t.card_id,
            ticker=t.ticker,
            dates=(f"{day(to_et(t.opened_at).date())} – " if t.opened_at else "")
            + day(to_et(t.closed_at).date()),
            mode=t.mode or "—",
            result_share=percent(t.pnl / capital, signed=True),
            result=money(t.pnl, signed=True),
            exit_reason=t.exit_reason or "—",
        )
        for t in reversed(closed)
    ]
    if closed:
        wins = sum(t.pnl > 0 for t in closed)
        total = money(sum(t.pnl for t in closed), signed=True).display
        view.total = (
            f"Сделок {count(len(closed)).display} · прибыльных {count(wins).display} · итог {total}"
        )
    else:
        view.message = "нет закрытых сделок"
    return view


def card_view(session: Session, card_id: int) -> Card | None:
    row = session.execute(
        select(orm.TradeCard, orm.Decision.mode, orm.Event.ticker)
        .join(orm.Decision, orm.Decision.id == orm.TradeCard.decision_id)
        .join(orm.Event, orm.Event.id == orm.Decision.event_id)
        .where(orm.TradeCard.id == card_id)
    ).first()
    if row is None:
        return None
    card, mode, ticker = row
    transitions = session.scalars(
        select(orm.TradeCardTransition)
        .where(orm.TradeCardTransition.card_id == card_id)
        .order_by(orm.TradeCardTransition.at)
    ).all()
    return Card(
        card_id=card.id,
        ticker=ticker,
        mode=mode or "—",
        state=card.state,
        is_paper=card.paper,
        legs=str(card.legs),
        transitions=[
            Transition(
                time=f"{day(to_et(t.at).date())} {et_msk(t.at)}",
                change=f"{t.from_state or '—'} → {t.to_state}",
                reason=t.reason or "—",
            )
            for t in transitions
        ],
    )
