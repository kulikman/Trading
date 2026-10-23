"""Карточки сделок (SPEC §11): создание и состав позиции. Переходы — core.state_machine.card."""

import math
from datetime import datetime

from sqlalchemy.orm import Session

from backtest.simulate import Trade
from core.db import models as orm
from core.domain.trading import CardFill, CardLeg, CardPlan, TradePlan
from core.state_machine.card import start


def open_card(
    session: Session, decision: orm.Decision, plan: CardPlan | None = None
) -> orm.TradeCard:
    """Карточка paper-сделки для нового входа: PLANNED с момента решения.

    plan — лимит, стоп и число акций для сигнала (акция режима C); у опционов его нет.
    """
    card = orm.TradeCard(
        decision_id=decision.id,
        state="PLANNED",
        paper=True,
        legs=[],
        plan=None if plan is None else plan.model_dump(mode="json"),
    )
    session.add(card)
    session.flush()
    start(session, card, decision.decided_at, "сигнал")
    return card


def stock_plan_of(plan: TradePlan | None, risk_usd: float) -> CardPlan | None:
    """План акции из плана предложения: лимит входа, стоп и целые акции под риск карточки.

    Нет плана, ордера входа или стопа — None (опционы и предложения без плана).
    """
    if plan is None:
        return None
    entry = next((o for o in plan.orders if o.purpose == "entry"), None)
    stop = next((o for o in plan.orders if o.purpose == "stop"), None)
    if entry is None or stop is None or entry.limit_price is None or stop.stop_price is None:
        return None
    distance = abs(entry.limit_price - stop.stop_price)
    if distance <= 0 or risk_usd <= 0:
        return None
    return CardPlan(
        limit_price=entry.limit_price,
        stop_price=stop.stop_price,
        stop_distance=distance,
        shares=max(1, math.floor(risk_usd / distance)),
        risk_usd=risk_usd,
        entry_until=plan.entry_until_et,
    )


def legs_of(trade: Trade, scale: float) -> list[CardLeg]:
    """Ноги позиции: scale — доля позиции бэктеста, дающая риск сделки (у paper — дробная)."""
    return [
        CardLeg(
            symbol=leg.symbol,
            instrument=leg.instrument,
            side="buy" if leg.side == 1 else "sell",
            quantity=leg.quantity * scale,
            multiplier=leg.multiplier,
        )
        for leg in trade.legs
    ]


def entry_fills(trade: Trade, scale: float, at: datetime) -> list[CardFill]:
    return [
        CardFill(
            symbol=leg.symbol,
            side="buy" if leg.side == 1 else "sell",
            quantity=leg.quantity * scale,
            price=leg.entry_price,
            at=at,
            purpose="entry",
        )
        for leg in trade.legs
    ]


def exit_fills(trade: Trade, scale: float) -> list[CardFill]:
    return [
        CardFill(
            symbol=leg.symbol,
            side="sell" if leg.side == 1 else "buy",
            quantity=leg.quantity * scale,
            price=leg.exit_price,
            at=trade.exit_at,
            purpose="stop" if trade.exit_reason in ("stop", "trail_stop") else "exit",
        )
        for leg in trade.legs
    ]
