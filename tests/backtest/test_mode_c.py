from datetime import date, datetime, time

import pytest

from adapters.massive.models import Bar
from backtest.mode_c import (
    Entry,
    average_true_range,
    direction_of,
    entry,
    exit_after,
    first_hour,
)
from core.config import load_config
from core.session_guard import ET, next_trading_day, previous_trading_day

THRESHOLDS = load_config().thresholds
RULES = (
    THRESHOLDS.modes.C
)  # сюрприз 5%, объём 2×, лимит VWAP ± 0,3%, трейлинг 2 ATR(14), SMA5, 20 дней
SETTINGS = THRESHOLDS.backtest.mode_c
REACTION = date(2025, 10, 22)
ENTRY_AT = datetime.combine(REACTION, time(10, 31), tzinfo=ET)


def minute(
    day: date,
    hh: int,
    mm: int,
    close: float,
    volume: float = 100,
    *,
    open_: float | None = None,
    high: float | None = None,
    low: float | None = None,
    vwap: float | None = None,
) -> Bar:
    start = datetime.combine(day, time(hh, mm), tzinfo=ET)
    return Bar.model_validate(
        {
            "o": close if open_ is None else open_,
            "h": close if high is None else high,
            "l": close if low is None else low,
            "c": close,
            "v": volume,
            "vw": close if vwap is None else vwap,
            "t": start.timestamp() * 1000,
        }
    )


def history(days: int, volume: float = 1000) -> tuple[list[date], list[Bar]]:
    out, day = [], REACTION
    for _ in range(days):
        day = previous_trading_day(day)
        out.append(day)
    return out, [minute(d, 9, 31, 100, volume) for d in out]


def reaction_minutes(
    volume: float = 3000, price_1029: float = 106, open_1031: float = 106, low_1031: float = 105
) -> list[Bar]:
    return [
        minute(REACTION, 9, 31, 105, volume, vwap=105),
        minute(REACTION, 10, 29, price_1029),  # объём 100 — тоже первый час
        minute(REACTION, 10, 31, 106, open_=open_1031, low=low_1031, high=107),
    ]


def first_hour_vwap(volume: float = 3000, price_1029: float = 106) -> float:
    return (105 * volume + price_1029 * 100) / (volume + 100)


@pytest.mark.parametrize(
    ("surprise", "expected"), [(6.0, 1), (-6.0, -1), (4.9, None), (None, None)]
)
def test_direction_needs_surprise_above_threshold(
    surprise: float | None, expected: int | None
) -> None:
    assert direction_of(surprise, RULES) == expected


def test_first_hour_volume_and_vwap() -> None:
    bars = [
        minute(REACTION, 9, 30, 10, 100, vwap=10),
        minute(REACTION, 10, 0, 12, 300, vwap=12),
        minute(REACTION, 10, 30, 50, 999),  # 10:30 — уже не первый час
    ]
    volume, vwap = first_hour(bars, REACTION)
    assert volume == 400
    assert vwap == pytest.approx((10 * 100 + 12 * 300) / 400)


def test_long_entry_fills_at_vwap_limit() -> None:
    days, past = history(20)
    result = entry(1, 100.0, REACTION, [*past, *reaction_minutes()], days, RULES, SETTINGS)
    assert isinstance(result, Entry)
    # лимит = VWAP первого часа × 1,003 = 105,347;
    # открытие 10:31 (106) выше лимита, минимум 105 — исполнено по лимиту
    assert result.price == pytest.approx(first_hour_vwap() * 1.003)
    assert result.at == ENTRY_AT


def test_open_below_limit_fills_at_open() -> None:
    days, past = history(20)
    bars = [*past, *reaction_minutes(open_1031=105.1)]
    result = entry(1, 100.0, REACTION, bars, days, RULES, SETTINGS)
    assert isinstance(result, Entry)
    assert result.price == 105.1


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"price_1029": 99}, "no_price_confirm"),  # к 10:30 цена ниже закрытия накануне
        ({"volume": 1800}, "no_volume_confirm"),  # первый час 1800 + 100 ≤ 2 × 1000
        ({"low_1031": 105.4}, "not_filled"),  # до 11:00 лимит 105,347 не достигнут
    ],
)
def test_entry_rejections(kwargs: dict[str, float], reason: str) -> None:
    days, past = history(20)
    bars = [*past, *reaction_minutes(**kwargs)]
    assert entry(1, 100.0, REACTION, bars, days, RULES, SETTINGS) == reason


def test_short_volume_history_means_no_entry() -> None:
    days, past = history(9)
    bars = [*past, *reaction_minutes()]
    assert entry(1, 100.0, REACTION, bars, days, RULES, SETTINGS) == "no_volume_history"


def test_short_entry_sells_not_below_limit() -> None:
    days, past = history(20)
    bars = [
        *past,
        minute(REACTION, 9, 31, 95, 3000, vwap=95),
        minute(REACTION, 10, 29, 94),
        minute(REACTION, 10, 31, 94, high=95.5, low=93.5),
    ]
    result = entry(-1, 100.0, REACTION, bars, days, RULES, SETTINGS)
    assert isinstance(result, Entry)
    # продажа: лимит — не ниже VWAP × 0,997 = 94,683;
    # открытие 94 хуже лимита, максимум 95,5 — исполнено по лимиту
    assert result.price == pytest.approx((95 * 3000 + 94 * 100) / 3100 * 0.997)


def day_bar(day: date, close: float, high: float, low: float, open_: float | None = None) -> Bar:
    start = datetime.combine(day, time(0), tzinfo=ET)
    return Bar.model_validate(
        {
            "o": close if open_ is None else open_,
            "h": high,
            "l": low,
            "c": close,
            "v": 1e6,
            "t": start.timestamp() * 1000,
        }
    )


def flat_history(days: int = 15) -> list[Bar]:
    out, day = [], REACTION
    for _ in range(days):
        day = previous_trading_day(day)
        out.append(day_bar(day, 100, 101, 99))
    return list(reversed(out))


def test_average_true_range() -> None:
    assert average_true_range(flat_history(), 14) == pytest.approx(2.0)
    assert average_true_range(flat_history(14), 14) is None  # нужно 15 свечей


def test_trailing_stop_follows_close_then_gap_exits_at_open() -> None:
    day1 = next_trading_day(REACTION)
    day2 = next_trading_day(day1)
    daily = [
        *flat_history(),
        day_bar(REACTION, 106, 107, 104),
        day_bar(day1, 108, 109, 106),
        day_bar(day2, 100, 101, 99, open_=100),
    ]
    result = exit_after(Entry(1, 105.0, ENTRY_AT), daily, REACTION, RULES)
    # стоп: 105 − 2·2 = 101 → после дня входа 101,29 → после дня 1: 108 − 2·2,4286 = 103,14;
    # день 2 открылся на 100 — ниже стопа: выход по открытию
    assert result is not None
    assert (result.reason, result.price) == ("trail_stop", 100)
    assert result.at == datetime.combine(day2, time(9, 30), tzinfo=ET)


def test_close_below_sma_exits() -> None:
    day1 = next_trading_day(REACTION)
    daily = [
        *flat_history(),
        day_bar(REACTION, 106, 107, 104),
        day_bar(day1, 101.4, 106, 101.35),
    ]
    result = exit_after(Entry(1, 105.0, ENTRY_AT), daily, REACTION, RULES)
    # стоп 101,29 не задет (минимум 101,35); SMA5 = (100·3 + 106 + 101,4) / 5 = 101,48 > 101,4
    assert result is not None
    assert (result.reason, result.price) == ("sma", 101.4)


def test_max_hold_exits_after_twenty_days() -> None:
    daily, day, price = flat_history(), REACTION, 100.0
    for _ in range(25):
        price += 1
        daily.append(day_bar(day, price, price + 0.5, price - 0.5))
        day = next_trading_day(day)
    result = exit_after(Entry(1, 101.0, ENTRY_AT), daily, REACTION, RULES)
    assert result is not None
    assert (result.reason, result.price) == ("max_hold", 121.0)  # 20 торговых дней после входа


def test_open_position_at_history_end_is_none() -> None:
    daily = [*flat_history(), day_bar(REACTION, 106, 107, 104)]
    assert exit_after(Entry(1, 105.0, ENTRY_AT), daily, REACTION, RULES) is None
    assert exit_after(Entry(1, 105.0, ENTRY_AT), [], REACTION, RULES) is None
