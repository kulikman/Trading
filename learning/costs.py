"""Калибровка издержек (T21, SPEC §17 п.3): издержки Paper (CostModel) против реальных исполнений.

Реальные издержки ноги — насколько исполнение хуже намеченной цены ордера (лимит или стоп).
Допущение: намеченная цена — опорная (середина или теоретическая), от неё же CostModel считает
спред и проскальзывание; исполнение лучше намеченной — реальные ниже модели. Комиссия в сравнение
не входит — она по тарифу брокера.

Не считаются: рыночный ордер (намеченной цены нет) и исполнение ровно по намеченной цене — так
подтверждает кнопка «Исполнено», цены она не измеряет (настоящее исполнение ровно по лимиту
тоже выпадает — выборка смещена к исполнениям с улучшением). Источника фактических цен пока нет:
ордера Real в broker_order система не создаёт, ввод цены исполнения — решение заказчика.

От `min_fills` исполнений и расхождении больше `costs.paper_vs_real_alert` — сообщение «СИСТЕМА»
с поправкой допущения спреда; конфиг брокера меняет заказчик.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import models as orm
from core.domain.broker import Fill, Order
from core.text import plural
from execution.costs import CostLeg, CostModel

DRIFT_CODE = "COSTS_DRIFT"
NO_FILLS = "нет данных до реальных исполнений"


@dataclass(frozen=True)
class RealExecution:
    """Исполнение Real-ордера с намеченной ценой."""

    order: Order
    fill: Fill

    @property
    def intended(self) -> float | None:
        return self.order.limit_price or self.order.stop_price


@dataclass(frozen=True)
class CostCalibration:
    fills: int
    model_cost: float  # $, спред + проскальзывание по модели
    real_cost: float  # $, исполнение хуже намеченной цены
    divergence: float | None  # реальные / модельные − 1
    drift: bool
    enough: bool  # исполнений не меньше min_fills — можно делать вывод
    text: str


def compare_costs(
    executions: Iterable[RealExecution], model: CostModel, *, alert: float, min_fills: int
) -> CostCalibration:
    """Суммы по всем измеримым исполнениям; drift — от min_fills и расхождение больше alert."""
    model_cost = real_cost = 0.0
    fills = 0
    for execution in executions:
        intended = execution.intended
        if intended is None:
            continue
        fill = execution.fill
        units = fill.quantity * fill.multiplier
        sign = 1 if fill.side == "buy" else -1
        real_cost += sign * (fill.price - intended) * units
        leg = CostLeg(fill.instrument, fill.quantity, fill.multiplier, intended)
        expected = model.leg_cost(leg, at_open=False)
        model_cost += expected.spread + expected.slippage
        fills += 1
    if fills == 0 or model_cost <= 0:
        return CostCalibration(fills, model_cost, real_cost, None, False, False, NO_FILLS)
    divergence = real_cost / model_cost - 1
    enough = fills >= min_fills
    drift = enough and abs(divergence) > alert
    side = "выше" if divergence > 0 else "ниже"
    text = (
        f"реальные {side} модели на {abs(divergence):.0%} "
        f"({fills} {plural(fills, 'исполнение', 'исполнения', 'исполнений')})"
    )
    if not enough:
        text += f", вывод — от {min_fills}"
    return CostCalibration(fills, model_cost, real_cost, divergence, drift, enough, text)


def real_executions(session: Session) -> list[RealExecution]:
    """Исполнения ордеров брокера, кроме подтверждений кнопкой по намеченной цене."""
    found: list[RealExecution] = []
    for row in session.scalars(select(orm.BrokerOrder).where(orm.BrokerOrder.status == "filled")):
        if row.fill is None:
            continue
        execution = RealExecution(
            Order.model_validate(row.payload, strict=False),
            Fill.model_validate(row.fill, strict=False),
        )
        if execution.fill.price != execution.intended:
            found.append(execution)
    return found


def check_costs(
    session: Session, model: CostModel, *, alert: float, min_fills: int, now: datetime
) -> CostCalibration:
    """Сверка; при расхождении — сообщение «СИСТЕМА» (одно на каждый новый итог)."""
    result = compare_costs(real_executions(session), model, alert=alert, min_fills=min_fills)
    if not result.drift or result.divergence is None:
        return result
    factor = result.real_cost / result.model_cost
    advice = (
        f"допущение спреда × {factor:.2f}"
        if factor > 0
        else "исполнения не хуже намеченных цен — допущение спреда можно снизить"
    )
    text = (
        f"СИСТЕМА · издержки Paper против реальности: {result.text}, порог {alert:.0%}. "
        f"Пересчитать CostModel (config/broker.yaml): {advice}"
    )
    sent = session.scalar(
        select(orm.SystemMessage.id).where(
            orm.SystemMessage.code == DRIFT_CODE, orm.SystemMessage.text == text
        )
    )
    if sent is None:
        session.add(orm.SystemMessage(at=now, code=DRIFT_CODE, text=text))
    return result
