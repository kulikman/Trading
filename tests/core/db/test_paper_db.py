from datetime import UTC, date, datetime, time
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.massive.history import EventDays
from backtest.simulate import ExitReason, LegFill, Trade
from core.config import load_config
from core.db import models as orm
from core.db.store import sync_universe
from core.session_guard import ET
from execution.cards import open_card
from execution.paper import PaperBook
from learning.shadow import Shadow

CONFIG = load_config()
REPORT = date(2026, 10, 20)  # вторник BMO: реакция 20.10, вход накануне 19.10
AT = datetime(2026, 10, 19, 19, 10, tzinfo=UTC)
EXIT_AT = datetime.combine(REPORT, time(10, 5), tzinfo=ET)


class Calculator:
    def __init__(self, outcome: Shadow) -> None:
        self.outcome, self.calls = outcome, 0

    def evaluate(
        self,
        session: Session,
        step: orm.DecisionStep,
        event: orm.Event,
        days: EventDays,
        today: date,
    ) -> Shadow:
        self.calls += 1
        return self.outcome


def trade(reason: ExitReason = "target") -> Trade:
    """Кондор: return on risk (60 − 5) / 110 = 0,5."""
    return Trade(
        ticker="NFLX",
        report_date=REPORT,
        construction="iron_condor",
        entry_value=1.2,
        exit_value=0.6,
        exit_reason=reason,
        exit_at=EXIT_AT,
        gross_pnl=60,
        costs=5,
        risk=110,
        entry_on=date(2026, 10, 19),
        legs=(
            LegFill("O:NFLX261023P00900000", "option", -1, 1, 100, 0.8, 0.4),
            LegFill("O:NFLX261023P00850000", "option", 1, 1, 100, 0.2, 0.1),
        ),
    )


@pytest.fixture
def card(session: Session) -> orm.TradeCard:
    sync_universe(session, CONFIG.universe)
    event = orm.Event(ticker="NFLX", report_date=REPORT, report_time="BMO", date_status="confirmed")
    session.add(event)
    session.flush()
    session.add(
        orm.DecisionStep(
            event_id=event.id,
            stage="T-1",
            job="mode_b_decision",
            strategy_id="iron_condor",
            is_shadow=False,
            outcome="proposal",
            mode="move",
            construction="iron_condor",
            edge=0.0,
            confidence=0.6,
            probability=0.6,
            risk_fraction=0.01,
            at=AT,
        )
    )
    decision = orm.Decision(
        event_id=event.id,
        status="ENTERED",
        strategy_id="iron_condor",
        construction="iron_condor",
        mode="move",
        decided_at=AT,
    )
    session.add(decision)
    session.flush()
    return open_card(session, decision)


def path(session: Session) -> list[tuple[str | None, str, str | None]]:
    rows = session.scalars(select(orm.TradeCardTransition).order_by(orm.TradeCardTransition.id))
    return [(r.from_state, r.to_state, r.reason) for r in rows]


def test_closed_trade_goes_planned_open_closed(session: Session, card: orm.TradeCard) -> None:
    outcome = Shadow("closed", trade=trade())
    result = PaperBook(Calculator(outcome), CONFIG.thresholds).run(
        session, date(2026, 10, 21), date(2026, 10, 14)
    )
    assert result.counts == {"CLOSED": 1}
    assert path(session) == [
        (None, "PLANNED", "сигнал"),
        ("PLANNED", "ARMED", "ордер на вход"),
        ("ARMED", "OPEN", "вход"),
        ("OPEN", "CLOSING", "ордер на выход"),
        ("CLOSING", "CLOSED", "target"),
    ]
    # return on risk 0,5 × риск сделки 1% от 100 000
    assert card.pnl_total == Decimal("500.00")
    scale = 1000 / 110  # доля позиции бэктеста (риск 110 $ на контракт) для риска 1 000 $
    assert card.legs[0] == {
        "symbol": "O:NFLX261023P00900000",
        "instrument": "option",
        "side": "sell",
        "quantity": pytest.approx(scale),
        "multiplier": 100,
    }
    assert [(f["purpose"], f["side"], f["price"]) for f in card.fills or []] == [
        ("entry", "sell", 0.8),
        ("entry", "buy", 0.2),
        ("exit", "buy", 0.4),
        ("exit", "sell", 0.1),
    ]
    assert card.stop == {"rule": "убыток 2× премии", "price": None}
    calculator = Calculator(outcome)
    PaperBook(calculator, CONFIG.thresholds).run(session, date(2026, 10, 22), date(2026, 10, 14))
    assert calculator.calls == 0  # закрытая карточка не пересчитывается


def test_stop_and_open_and_waiting(session: Session, card: orm.TradeCard) -> None:
    book = PaperBook(Calculator(Shadow("open", "open_at_end", trade=trade())), CONFIG.thresholds)
    assert book.run(session, REPORT, date(2026, 10, 14)).counts == {}  # реакция ещё не закрылась
    assert book.run(session, date(2026, 10, 21), date(2026, 10, 14)).counts == {"OPEN": 1}
    assert card.pnl_total is None
    stop = PaperBook(Calculator(Shadow("closed", trade=trade("stop"))), CONFIG.thresholds)
    stop.run(session, date(2026, 10, 22), date(2026, 10, 14))
    assert path(session)[-1] == ("OPEN", "STOPPED", "stop")
    assert [f["purpose"] for f in card.fills or []][-1] == "stop"


def test_no_data_waits_then_cancels(session: Session, card: orm.TradeCard) -> None:
    book = PaperBook(Calculator(Shadow("no_data", "no_exit_price")), CONFIG.thresholds)
    assert book.run(session, date(2026, 10, 21), date(2026, 10, 14)).counts == {"PLANNED": 1}
    assert book.run(session, date(2026, 10, 28), date(2026, 10, 21)).counts == {"CANCELLED": 1}
    assert path(session)[-1] == ("PLANNED", "CANCELLED", "no_exit_price")
