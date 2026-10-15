"""Real-карточка (E10): размер по SPEC от капитала Real, ордера человеку через ручного брокера.

Стратегия в стадии live_small / live (подъём только `promote` по метрикам — решение заказчика
15.10.2026) при прошедшем решении получает, кроме paper-карточки, Real-карточку:
риск = капитал Real (пополнения `make cash`) × size_real (Келли или фиксированный риск без модели,
Black Swan, вес стадии, × 0,5 первые 30 дней); единиц = риск / риск единицы плана стратегии
(вниз до целого). Ордера плана × единиц ставятся ManualBroker в broker_order — человек видит их
в карточке «ДЕЙСТВИЕ» и подтверждает в боте. Карточка: PLANNED → ARMED (ордера выставлены).
Не открылась — причина словами (её показывает «СИСТЕМА»).
"""

import math
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from adapters.broker.base import CardOrders
from core.config.thresholds import Thresholds
from core.db import models as orm
from core.domain.trading import CardLeg, CardStop
from core.registry.protocols import Proposal
from core.risk.black_swan import Level
from core.session_guard import to_et
from core.state_machine.card import start, transition
from decision.capital import Rejection, size_real
from execution.cash import real_capital


@dataclass(frozen=True)
class RealOutcome:
    card_id: int | None
    reason: str


def first_real_day(session: Session) -> date | None:
    """День первого пополнения счёта Real — отсчёт «первых 30 дней» (SPEC §14, фаза 4)."""
    first = session.scalar(
        select(func.min(orm.CashMovement.at)).where(orm.CashMovement.account == "real")
    )
    return None if first is None else to_et(first).date()


def open_real_card(
    session: Session,
    decision: orm.Decision,
    proposal: Proposal,
    *,
    level: Level,
    b: float,
    seasons_1_2: bool,
    weight: float,
    no_model: bool,
    thresholds: Thresholds,
    orders: CardOrders,
    now: datetime,
) -> RealOutcome:
    plan = proposal.plan
    if plan is None:
        return RealOutcome(None, f"у конструкции {proposal.construction} нет плана ордеров")
    if plan.entry_until_et is not None and to_et(now).time() >= plan.entry_until_et:
        return RealOutcome(None, f"окно входа до {plan.entry_until_et:%H:%M} ET прошло")
    capital = real_capital(session)
    if capital is None or capital <= 0:
        return RealOutcome(None, "счёт Real не пополнен (make cash)")
    first = first_real_day(session)
    first_days = first is not None and (to_et(now).date() - first).days < (
        thresholds.sizing.real_first_days
    )
    sizing = size_real(
        proposal,
        level=level,
        b=b,
        seasons_1_2=seasons_1_2,
        weight=weight,
        first_days=first_days,
        no_model=no_model,
        thresholds=thresholds,
    )
    if isinstance(sizing, Rejection):
        return RealOutcome(None, "отказ: " + ", ".join(sizing.reasons))
    risk_usd = capital * sizing.risk_fraction
    units = math.floor(risk_usd / plan.unit_risk)
    if units < 1:
        return RealOutcome(
            None, f"риск ${risk_usd:.2f} меньше одной единицы (${plan.unit_risk:.2f})"
        )
    card = orm.TradeCard(
        decision_id=decision.id,
        state="PLANNED",
        paper=False,
        legs=[
            CardLeg(
                symbol=o.symbol,
                instrument=o.instrument,
                side=o.side,
                quantity=o.quantity * units,
                multiplier=o.multiplier,
            ).model_dump(mode="json")
            for o in plan.orders
            if o.purpose == "entry"
        ],
        stop=CardStop(
            rule=plan.stop_rule,
            price=next((o.stop_price for o in plan.orders if o.purpose == "stop"), None),
        ).model_dump(mode="json"),
        risk_usd=Decimal(str(round(units * plan.unit_risk, 2))),
    )
    session.add(card)
    session.flush()
    start(session, card, now, "сигнал Real")
    for n, order in enumerate(plan.orders):
        orders.place_for_card(
            order.model_copy(
                update={
                    "client_order_id": f"card-{card.id}-{n}",
                    "quantity": order.quantity * units,
                }
            ),
            card.id,
        )
    transition(session, card, "ARMED", now, "ордера выставлены человеку")
    return RealOutcome(card.id, f"{units} ед., риск ${units * plan.unit_risk:,.0f}")
