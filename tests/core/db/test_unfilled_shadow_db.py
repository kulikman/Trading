"""Теневой «вход по рынку» для карточек, не исполненных по лимиту (сбор данных, без сигналов)."""

from datetime import date, datetime, time
from typing import Any

import pytest
from sqlalchemy.orm import Session

from adapters.massive.models import Bar
from backtest.mode_c import Entry
from backtest.simulate import LegFill, Trade
from core.session_guard import ET, to_et
from execution.paper_fill import fill_planned_cards
from execution.unfilled_shadow import UnfilledShadow, unfilled_summary
from learning.shadow import Shadow
from tests.core.db.test_paper_fill_db import (
    NOW,
    REACTION,
    THRESHOLDS,
    Stocks,
    planned_card,
)

TODAY = date(2025, 10, 23)  # реакция 22.10 уже прошла
RETRY_SINCE = date(2025, 10, 16)


class Calculator:
    def __init__(self, outcome: Shadow) -> None:
        self.outcome = outcome
        self.entries: list[Entry | None] = []

    def evaluate(
        self,
        session: Session,
        step: Any,
        event: Any,
        days: Any,
        today: date,
        fixed_entry: Entry | None = None,
    ) -> Shadow:
        self.entries.append(fixed_entry)
        return self.outcome


class NoBarsAfterSignal(Stocks):
    def aggregates(
        self, ticker: str, multiplier: int, timespan: str, start: date, end: date, **kwargs: Any
    ) -> list[Bar]:
        bars = super().aggregates(ticker, multiplier, timespan, start, end, **kwargs)
        if timespan != "minute":
            return bars
        return [
            b
            for b in bars
            if not (to_et(b.start).date() == REACTION and to_et(b.start).time() >= time(10, 31))
        ]


def trade(gross: float) -> Trade:
    """Покупка 250 акций по 106 (вход по рынку в 10:46); итог — gross − 5 издержек, риск 1005."""
    return Trade(
        ticker="NFLX",
        report_date=REACTION,
        construction="mode_c",
        entry_value=106.0,
        exit_value=101.0,
        exit_reason="trail_stop",
        exit_at=datetime(2025, 10, 23, 9, 30, tzinfo=ET),
        gross_pnl=gross,
        costs=5.0,
        risk=1005.0,
        variant="long",
        entry_on=REACTION,
        entry_at=datetime(2025, 10, 22, 10, 46, tzinfo=ET),
        legs=(LegFill("NFLX", "stock", 1, 250, 1, 106.0, 101.0),),
    )


def cancelled_card(session: Session) -> Any:
    _, _, card = planned_card(session)
    stocks = Stocks(low_after_signal=105.4, late_bar=True)  # лимит не достигнут — отмена
    fill_planned_cards(session, stocks, THRESHOLDS, NOW, closed_after=time(16, 30))
    assert card.state == "CANCELLED"
    return card


def shadow(calculator: Calculator, stocks: Stocks | None = None) -> UnfilledShadow:
    return UnfilledShadow(calculator, stocks or Stocks(low_after_signal=105.4), THRESHOLDS)


def test_market_entry_is_taken_on_the_first_minute_after_the_signal(session: Session) -> None:
    card = cancelled_card(session)
    calculator = Calculator(Shadow("closed", trade=trade(-1250.0)))
    result = shadow(calculator).run(session, TODAY, RETRY_SINCE)
    assert result.counts == {"closed": 1}
    [entry] = calculator.entries
    assert entry is not None
    assert (entry.price, entry.at) == (106.0, datetime(2025, 10, 22, 10, 46, tzinfo=ET))
    found = card.counterfactual
    assert found["status"] == "closed"
    assert found["return_on_risk"] == pytest.approx(-1255.0 / 1005.0)
    assert found["pnl_usd"] == pytest.approx(-1255.0 / 1005.0 * 1000.0)  # риск карточки 1% = $1 000
    assert found["exit_reason"] == "trail_stop"


def test_closed_result_is_not_recalculated_but_open_one_is(session: Session) -> None:
    card = cancelled_card(session)
    still_open = Calculator(Shadow("open", "open_at_end"))
    shadow(still_open).run(session, TODAY, RETRY_SINCE)
    assert card.counterfactual["status"] == "open"
    assert card.counterfactual["entry_price"] == 106.0
    closing = Calculator(Shadow("closed", trade=trade(500.0)))
    shadow(closing).run(session, TODAY, RETRY_SINCE)  # открытая позиция пересчитывается
    assert card.counterfactual["status"] == "closed"
    assert len(closing.entries) == 1
    again = Calculator(Shadow("closed", trade=trade(-9999.0)))
    shadow(again).run(session, TODAY, RETRY_SINCE)  # закрытая — нет
    assert again.entries == []
    assert card.counterfactual["return_on_risk"] == pytest.approx(495.0 / 1005.0)


def test_reaction_day_is_not_calculated_yet(session: Session) -> None:
    card = cancelled_card(session)
    calculator = Calculator(Shadow("closed", trade=trade(500.0)))
    result = shadow(calculator).run(session, REACTION, RETRY_SINCE)
    assert result.counts == {}
    assert card.counterfactual is None
    assert calculator.entries == []


def test_no_bars_after_the_signal_means_no_data(session: Session) -> None:
    card = cancelled_card(session)
    calculator = Calculator(Shadow("closed", trade=trade(500.0)))
    result = shadow(calculator, NoBarsAfterSignal(low_after_signal=105.4)).run(
        session, TODAY, RETRY_SINCE
    )
    assert result.counts == {"no_data": 1}
    assert card.counterfactual["note"] == "no_bars_after_signal"
    assert calculator.entries == []


def test_only_cancelled_cards_get_a_shadow_entry(session: Session) -> None:
    _, _, card = planned_card(session)  # PLANNED — не отменена
    calculator = Calculator(Shadow("closed", trade=trade(500.0)))
    result = shadow(calculator).run(session, TODAY, RETRY_SINCE)
    assert result.counts == {}
    assert card.counterfactual is None


def test_summary_counts_closed_open_and_missing(session: Session) -> None:
    cancelled_card(session)
    assert unfilled_summary(session).cards == 0  # посчитанных ещё нет
    shadow(Calculator(Shadow("closed", trade=trade(-1250.0)))).run(session, TODAY, RETRY_SINCE)
    summary = unfilled_summary(session)
    assert (summary.cards, summary.closed, summary.open, summary.no_data) == (1, 1, 0, 0)
    assert summary.mean_return == pytest.approx(-1255.0 / 1005.0)
    assert summary.win_rate == 0.0
