"""Карточки сделок (SPEC §11): создание и состав позиции. Переходы — core.state_machine.card."""

from datetime import datetime

from sqlalchemy.orm import Session

from backtest.simulate import Trade
from core.db import models as orm
from core.domain.trading import CardFill, CardLeg
from core.state_machine.card import start


def open_card(session: Session, decision: orm.Decision) -> orm.TradeCard:
    """Карточка paper-сделки для нового входа: PLANNED с момента решения."""
    card = orm.TradeCard(decision_id=decision.id, state="PLANNED", paper=True, legs=[])
    session.add(card)
    session.flush()
    start(session, card, decision.decided_at, "сигнал")
    return card


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
