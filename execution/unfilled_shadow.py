"""Теневой «вход по рынку на сигнале» для paper-карточек режима C, не исполненных по лимиту.

Решение заказчика 23.10.2026: лимит режима C (VWAP первого часа + 0,3%) иногда оказывается ниже
рынка, и сигнал не исполняется (TSLA 22.10). Основное правило не меняется; чтобы по данным решить,
стоит ли его ослаблять, для каждой отменённой карточки вечерний прогон считает, чем закончилась бы
покупка по рынку на первой минуте после сигнала: выход — по тем же правилам, что у paper
(трейлинг, SMA, срок). Результат — в `trade_card.counterfactual`; в Telegram, на сайт и в итоги
paper он не попадает. Сводка: `python -m execution.unfilled_shadow`.
"""

import logging
import statistics
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.massive.history import EventDays
from backtest.mode_c import Entry
from core.config.thresholds import Thresholds
from core.db import models as orm
from core.domain.trading import CardCounterfactual
from core.registry.agent_jobs import REPORT_TIMES
from core.session_guard import to_et
from execution.paper import Evaluator, entry_step
from execution.paper_fill import StockData, minute_after, reaction_minutes

logger = logging.getLogger(__name__)


@dataclass
class UnfilledRunResult:
    counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class UnfilledSummary:
    cards: int
    closed: int
    open: int
    no_data: int
    mean_return: float | None  # среднее на $1 риска по закрытым
    win_rate: float | None


class UnfilledShadow:
    def __init__(self, calculator: Evaluator, stocks: StockData, thresholds: Thresholds) -> None:
        self._calculator = calculator
        self._stocks = stocks
        self._thresholds = thresholds

    def run(self, session: Session, today: date, retry_since: date) -> UnfilledRunResult:
        """Отменённые карточки закрывшихся событий: считает и обновляет теневой вход по рынку.

        Закрытые не пересчитываются; открытые — каждый вечер; без данных — пока реакция не
        старше retry_since.
        """
        result = UnfilledRunResult()
        rows = session.execute(
            select(orm.TradeCard, orm.Decision, orm.Event)
            .join(orm.Decision, orm.Decision.id == orm.TradeCard.decision_id)
            .join(orm.Event, orm.Event.id == orm.Decision.event_id)
            .where(
                orm.TradeCard.paper.is_(True),
                orm.TradeCard.state == "CANCELLED",
                orm.Decision.mode == "C",
            )
            .order_by(orm.TradeCard.id)
        ).all()
        now = datetime.now(UTC)
        for card, decision, event in rows:
            days = EventDays.of(event.report_date, REPORT_TIMES.get(event.report_time or ""))
            if days.reaction >= today:
                continue
            current = (
                CardCounterfactual.model_validate(card.counterfactual, strict=False)
                if card.counterfactual
                else None
            )
            if current is not None and (
                current.status == "closed"
                or (current.status == "no_data" and days.reaction < retry_since)
            ):
                continue
            found = self._evaluate(session, decision, event, days, today, now)
            card.counterfactual = found.model_dump(mode="json")
            result.counts[found.status] = result.counts.get(found.status, 0) + 1
        session.commit()
        logger.info("unfilled shadow", extra={"counts": result.counts})
        return result

    def _evaluate(
        self,
        session: Session,
        decision: orm.Decision,
        event: orm.Event,
        days: EventDays,
        today: date,
        now: datetime,
    ) -> CardCounterfactual:
        direction: Literal[1, -1] = 1 if decision.construction == "stock" else -1
        step = entry_step(session, decision)
        if step is None:
            return CardCounterfactual(status="no_data", note="no_step", updated_at=now)
        _, minutes = reaction_minutes(
            self._stocks,
            event.ticker,
            days.reaction,
            self._thresholds.backtest.mode_c.volume_lookback_days,
        )
        after = minute_after(decision.decided_at)
        bar = next(
            (b for b in minutes if to_et(b.start).date() == days.reaction and b.start >= after),
            None,
        )
        if bar is None:
            return CardCounterfactual(status="no_data", note="no_bars_after_signal", updated_at=now)
        entry = Entry(direction, bar.open, bar.start)
        outcome = self._calculator.evaluate(session, step, event, days, today, fixed_entry=entry)
        trade = outcome.trade
        if outcome.status == "closed" and trade is not None:
            risk_usd = self._thresholds.capital.module_usd * (step.risk_fraction or 0.0)
            return CardCounterfactual(
                status="closed",
                entry_price=entry.price,
                entry_at=entry.at,
                exit_price=trade.exit_value,
                exit_at=trade.exit_at,
                exit_reason=trade.exit_reason,
                return_on_risk=trade.return_on_risk,
                pnl_usd=trade.return_on_risk * risk_usd,
                updated_at=now,
            )
        if outcome.status == "open":
            return CardCounterfactual(
                status="open", entry_price=entry.price, entry_at=entry.at, updated_at=now
            )
        return CardCounterfactual(status="no_data", note=outcome.note, updated_at=now)


def unfilled_summary(session: Session) -> UnfilledSummary:
    """Сводка по отменённым карточкам с теневым входом: сколько и чем закончились."""
    cards = session.scalars(
        select(orm.TradeCard.counterfactual).where(
            orm.TradeCard.paper.is_(True), orm.TradeCard.state == "CANCELLED"
        )
    ).all()
    found = [CardCounterfactual.model_validate(c, strict=False) for c in cards if c]
    returns = [
        f.return_on_risk for f in found if f.status == "closed" and f.return_on_risk is not None
    ]
    return UnfilledSummary(
        cards=len(found),
        closed=len(returns),
        open=sum(f.status == "open" for f in found),
        no_data=sum(f.status == "no_data" for f in found),
        mean_return=statistics.fmean(returns) if returns else None,
        win_rate=sum(r > 0 for r in returns) / len(returns) if returns else None,
    )


def main() -> int:  # pragma: no cover
    """`python -m execution.unfilled_shadow`: сводка теневого входа по рынку."""
    from core.scheduler.jobs import engine

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    with Session(engine()) as session:
        s = unfilled_summary(session)
    mean = "—" if s.mean_return is None else f"{s.mean_return:+.3f}"
    wins = "—" if s.win_rate is None else f"{s.win_rate:.0%}"
    counts = f"закрыто {s.closed}, открыто {s.open}, нет данных {s.no_data}"
    logger.info(
        "Не исполнено по лимиту: %d; %s; среднее на $1 риска %s, выигрыш %s (по закрытым)",
        s.cards,
        counts,
        mean,
        wins,
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
