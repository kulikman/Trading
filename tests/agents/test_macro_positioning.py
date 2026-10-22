from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest

from adapters.errors import DataError
from adapters.fred.client import FredObservation
from adapters.massive.models import Bar, ShortInterest, TickerChange
from agents.macro.agent import MacroAgentPlugin, vix_closes
from agents.positioning.agent import PositioningAgentPlugin
from core.config import load_config
from core.registry.protocols import EventContext
from core.session_guard import ET, previous_trading_day

THRESHOLDS = load_config().thresholds
RUN_AT = datetime(2026, 10, 14, 11, 30, tzinfo=UTC)  # 07:30 ET, до открытия
CLOSE_DAY = date(2026, 10, 13)


def ctx() -> EventContext:
    return EventContext(
        event_id=1,
        ticker="NFLX",
        report_date=date(2026, 10, 21),
        report_time="AMC",
        stage="T-7",
        as_of=RUN_AT,
    )


def bar(day: date, close: float, volume: float = 1000.0) -> Bar:
    start = datetime.combine(day, time(0), tzinfo=ET).timestamp() * 1000
    return Bar.model_validate(
        {"o": close, "h": close, "l": close, "c": close, "v": volume, "t": start}
    )


def trading_days_until(day: date, count: int) -> list[date]:
    out = [day]
    for _ in range(count - 1):
        out.append(previous_trading_day(out[-1]))
    return list(reversed(out))


class Stocks:
    def __init__(self, bars: list[Bar], short: list[ShortInterest] | None = None) -> None:
        self.bars = bars
        self.short = short or []

    def aggregates(self, ticker: str, *args: Any, **kwargs: Any) -> list[Bar]:
        return self.bars

    def ticker_changes(self, ticker: str) -> list[TickerChange]:
        return []

    def short_interest(self, ticker: str, limit: int = 10) -> list[ShortInterest]:
        return self.short


class Fred:
    def __init__(self, series: dict[str, list[tuple[date, float | None]]]) -> None:
        self.series = series

    def observations(
        self, series_id: str, start: date | None = None, end: date | None = None
    ) -> list[FredObservation]:
        return [FredObservation(date=d, value=v) for d, v in self.series[series_id]]


def test_macro_features_at_previous_close() -> None:
    days = trading_days_until(CLOSE_DAY, 10)
    spy = [bar(d, 500.0) for d in days]
    # 26 — оранжевый по уровню, но рост за день 15 → 26 (+73%) — красный
    vix: list[tuple[date, float | None]] = [(d, 15.0) for d in days[:-1]]
    vix.append((CLOSE_DAY, 26.0))
    fred = Fred({"VIXCLS": vix, "DGS10": [(days[0], 4.20), (CLOSE_DAY, None), (days[-2], 4.25)]})
    agent = MacroAgentPlugin(
        fred, Stocks(spy), THRESHOLDS.risk_limits.black_swan, THRESHOLDS.agents.macro
    )
    features = agent.run(ctx())
    assert features.vix == 26.0
    assert features.us10y == pytest.approx(0.0425)  # пропуск FRED (".") не значение
    assert features.regime == 3  # рост VIX 15 → 26 за день (+73%) — красный


class DownFred:
    def observations(
        self, series_id: str, start: date | None = None, end: date | None = None
    ) -> list[FredObservation]:
        raise DataError("fred", "invalid JSON from https://api.stlouisfed.org/...")


class Cboe:
    def __init__(self, closes: dict[date, float] | None) -> None:
        self.closes = closes

    def vix_closes(self, start: date, end: date) -> dict[date, float]:
        if self.closes is None:
            raise DataError("cboe", "HTTP 503")
        return self.closes


def test_vix_uses_cboe_when_fred_is_down() -> None:
    cboe = Cboe({CLOSE_DAY: 16.7})
    assert vix_closes(DownFred(), cboe, CLOSE_DAY, CLOSE_DAY) == {CLOSE_DAY: 16.7}


def test_vix_uses_fred_when_cboe_is_down() -> None:
    fred = Fred({"VIXCLS": [(CLOSE_DAY, 16.0)]})
    assert vix_closes(fred, Cboe(None), CLOSE_DAY, CLOSE_DAY) == {CLOSE_DAY: 16.0}


def test_vix_fails_only_when_both_sources_are_down() -> None:
    with pytest.raises(DataError, match=r"fred — invalid JSON.*cboe — HTTP 503"):
        vix_closes(DownFred(), Cboe(None), CLOSE_DAY, CLOSE_DAY)
    with pytest.raises(DataError, match="invalid JSON"):
        vix_closes(DownFred(), None, CLOSE_DAY, CLOSE_DAY)  # CBOE не подключён — запасного нет


def test_macro_without_data_returns_empty_fields() -> None:
    agent = MacroAgentPlugin(
        Fred({"VIXCLS": [], "DGS10": []}),
        Stocks([]),
        THRESHOLDS.risk_limits.black_swan,
        THRESHOLDS.agents.macro,
    )
    features = agent.run(ctx())
    assert (features.vix, features.us10y, features.regime) == (None, None, None)


def test_positioning_by_hand() -> None:
    days = trading_days_until(CLOSE_DAY, 40)
    bars = [bar(d, 100.0 + i, 1000.0) for i, d in enumerate(days)]
    bars[-1] = bar(CLOSE_DAY, 139.0, 3000.0)  # вчера объём ×3
    bars.append(bar(date(2026, 10, 14), 999.0, 1e9))  # сегодняшний неполный день — не берём
    short = [
        ShortInterest(
            settlement_date=date(2026, 9, 30), ticker="NFLX", short_interest=1, days_to_cover=3.5
        ),
        ShortInterest(
            settlement_date=date(2026, 9, 15), ticker="NFLX", short_interest=1, days_to_cover=2.0
        ),
    ]
    agent = PositioningAgentPlugin(Stocks(bars, short), THRESHOLDS.agents.positioning)
    features = agent.run(ctx())
    anchor = [b for b, d in zip(bars, days, strict=False) if d <= CLOSE_DAY - timedelta(days=30)][
        -1
    ]
    assert features.pre_run_30d == pytest.approx(139.0 / anchor.close - 1)
    assert features.pre_run_3d == pytest.approx(139.0 / 136.0 - 1)  # 3 торговых дня назад — 136
    assert features.volume_anomaly == pytest.approx(3.0)
    # 30.09 + 12 дней = 12.10 ≤ 14.10 — уже опубликован
    assert features.short_interest_days == 3.5


def test_positioning_skips_unpublished_short_interest() -> None:
    days = trading_days_until(CLOSE_DAY, 40)
    short = [
        ShortInterest(
            settlement_date=date(2026, 10, 9), ticker="NFLX", short_interest=1, days_to_cover=9.0
        )
    ]
    agent = PositioningAgentPlugin(
        Stocks([bar(d, 100.0) for d in days], short), THRESHOLDS.agents.positioning
    )
    assert agent.run(ctx()).short_interest_days is None  # расчёт 09.10 к 14.10 ещё не опубликован


def test_positioning_needs_history() -> None:
    agent = PositioningAgentPlugin(Stocks([bar(CLOSE_DAY, 100.0)]), THRESHOLDS.agents.positioning)
    with pytest.raises(DataError, match="not enough daily bars"):
        agent.run(ctx())
