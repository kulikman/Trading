from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from adapters.massive.models import Bar, TickerChange
from core.config import load_config
from core.db import models as orm
from core.db.store import sync_universe
from core.domain.trading import CardFill
from core.session_guard import ET, previous_trading_day
from execution.trailing import update_trailing

CONFIG = load_config()
REACTION = date(2026, 10, 21)
NOW = datetime(2026, 10, 22, 20, 20, tzinfo=UTC)  # 16:20 ET на следующий день


class Stocks:
    """До входа — закрытия 100, диапазон 99–101 (ATR 2); день входа 106; следующий 108."""

    def aggregates(self, ticker: str, *args: Any, **kwargs: Any) -> list[Bar]:
        out, day = [], REACTION
        for _ in range(20):
            day = previous_trading_day(day)
            out.append(self._bar(day, 100, 101, 99))
        out = list(reversed(out))
        return [
            *out,
            self._bar(REACTION, 106, 107, 104),
            self._bar(date(2026, 10, 22), 108, 109, 106),
        ]

    def ticker_changes(self, ticker: str) -> list[TickerChange]:
        return []

    @staticmethod
    def _bar(day: date, c: float, h: float, low: float) -> Bar:
        start = datetime.combine(day, time(0), tzinfo=ET).timestamp() * 1000
        return Bar.model_validate({"o": c, "h": h, "l": low, "c": c, "v": 1, "t": start})


def card(session: Session, mode: str, state: str, with_fill: bool = True) -> orm.TradeCard:
    sync_universe(session, CONFIG.universe)
    event = orm.Event(
        ticker="NFLX", report_date=REACTION, report_time="BMO", date_status="confirmed"
    )
    session.add(event)
    session.flush()
    decision = orm.Decision(
        event_id=event.id,
        status="ENTERED",
        strategy_id=f"s_{mode}",
        construction="stock",
        mode=mode,
        decided_at=NOW - timedelta(days=1),
    )
    session.add(decision)
    session.flush()
    entry = CardFill(
        symbol="NFLX",
        side="buy",
        quantity=10,
        price=105.0,
        at=datetime.combine(REACTION, time(10, 45), tzinfo=ET),
        purpose="entry",
    )
    row = orm.TradeCard(
        decision_id=decision.id,
        state=state,
        paper=True,
        legs=[],
        fills=[entry.model_dump(mode="json")] if with_fill else [],
    )
    session.add(row)
    session.flush()
    return row


def test_open_mode_c_card_gets_trailing_stop(session: Session) -> None:
    open_c = card(session, "C", "OPEN")
    assert update_trailing(session, Stocks(), CONFIG.thresholds, NOW) == 1
    trailing = open_c.trailing or {}
    assert trailing["stop"] == pytest.approx(103.14, abs=0.01)  # как в бэктесте режима C
    assert trailing["multiple"] == 2.0
    assert trailing["updated_at"].startswith("2026-10-22T20:20")


@pytest.mark.parametrize(
    ("mode", "state", "with_fill"),
    [("move", "OPEN", True), ("C", "CLOSED", True), ("C", "OPEN", False)],
)
def test_other_cards_untouched(session: Session, mode: str, state: str, with_fill: bool) -> None:
    other = card(session, mode, state, with_fill)
    assert update_trailing(session, Stocks(), CONFIG.thresholds, NOW) == 0
    assert other.trailing is None
