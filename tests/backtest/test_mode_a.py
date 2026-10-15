from datetime import date, datetime, time, timedelta

import pytest

from adapters.massive.models import Bar
from backtest.mode_a import mode_a_trade
from backtest.simulate import Trade
from core.config import load_config
from core.session_guard import ET
from execution.costs import BrokerCostModel

CONFIG = load_config()
COSTS = BrokerCostModel(CONFIG.broker.costs["manual"])
START = date(2026, 9, 1)
ENTRY, EXIT = date(2026, 10, 13), date(2026, 10, 19)  # T−7 и T−1 (дни — по свечам ниже)


def bar(day: date, o: float, h: float, low: float, c: float) -> Bar:
    start = datetime.combine(day, time(0), tzinfo=ET).timestamp() * 1000
    return Bar.model_validate({"o": o, "h": h, "l": low, "c": c, "v": 1, "t": start})


def history(entry_close: float = 100.0, after: list[Bar] | None = None) -> list[Bar]:
    """До входа — закрытия 100 и диапазон 99–101 (ATR 2); вход T−7; потом after."""
    days = [START + timedelta(days=i) for i in range((ENTRY - START).days)]
    out = [bar(d, 100, 101, 99, 100) for d in days]
    out.append(bar(ENTRY, 100, 101, 99, entry_close))
    return out + (after or [])


def trade(daily: list[Bar]) -> Trade | str:
    return mode_a_trade(
        "NFLX",
        date(2026, 10, 20),
        ENTRY,
        EXIT,
        daily,
        thresholds=CONFIG.thresholds,
        costs=COSTS,
        capital=100_000,
    )


def test_holds_to_t_minus_1_close() -> None:
    result = trade(
        history(
            after=[bar(EXIT - timedelta(days=1), 100, 102, 99, 101), bar(EXIT, 101, 104, 100, 103)]
        )
    )
    assert isinstance(result, Trade)
    assert (result.exit_reason, result.exit_value) == ("time", 103)
    # стоп 1,5 × ATR 2 = 3; риск 1% от 100 000 → 333 акции
    assert result.gross_pnl == pytest.approx(3 * 333)
    assert 333 * 3 < result.risk < 333 * 3 + 10  # риск до стопа + издержки входа


def test_stop_on_gap_and_intraday() -> None:
    gap = trade(history(after=[bar(EXIT, 95, 96, 94, 95)]))
    assert isinstance(gap, Trade)
    assert (gap.exit_reason, gap.exit_value) == ("stop", 95)  # открытие ниже стопа 97
    touch = trade(history(after=[bar(EXIT, 99, 100, 96, 99)]))
    assert isinstance(touch, Trade)
    assert (touch.exit_reason, touch.exit_value) == ("stop", 97)


def test_no_entry() -> None:
    assert trade(history(entry_close=101)) == "not_filled"  # выше лимита по закрытию T−8
    assert trade(history()) == "open_at_end"  # свечи T−1 ещё нет
    assert trade([]) == "no_price"
