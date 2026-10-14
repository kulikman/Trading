from datetime import UTC, date, datetime
from typing import Any

import pytest

from core.session_guard import (
    ET,
    MSK,
    is_regular_session,
    is_trading_day,
    next_session_open,
    next_trading_day,
    previous_trading_day,
    reaction_day,
    session,
    shift_to_trading_day,
    to_et,
    to_msk,
    weekly_expiry,
)

# Праздники NYSE 2026 (биржевой календарь NYSE).
HOLIDAYS_2026 = [
    date(2026, 1, 1),  # New Year's Day
    date(2026, 1, 19),  # Martin Luther King Jr. Day
    date(2026, 2, 16),  # Washington's Birthday
    date(2026, 4, 3),  # Good Friday
    date(2026, 5, 25),  # Memorial Day
    date(2026, 6, 19),  # Juneteenth
    date(2026, 7, 3),  # Independence Day (observed)
    date(2026, 9, 7),  # Labor Day
    date(2026, 11, 26),  # Thanksgiving
    date(2026, 12, 25),  # Christmas
]
EARLY_CLOSES_2026 = [date(2026, 11, 27), date(2026, 12, 24)]  # закрытие 13:00 ET


def et(year: int, month: int, day: int, hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=ET)


# --- торговые дни ---


def test_regular_weekday_is_trading_day() -> None:
    assert is_trading_day(date(2026, 10, 13))


@pytest.mark.parametrize("day", [date(2026, 10, 17), date(2026, 10, 18)])
def test_weekend_is_not_trading_day(day: date) -> None:
    assert not is_trading_day(day)


@pytest.mark.parametrize("day", HOLIDAYS_2026, ids=str)
def test_holiday_is_not_trading_day(day: date) -> None:
    assert not is_trading_day(day)
    assert session(day) is None


def test_2026_holiday_list_is_complete() -> None:
    weekdays = [
        date.fromordinal(n)
        for n in range(date(2026, 1, 1).toordinal(), date(2026, 12, 31).toordinal() + 1)
    ]
    closed = [d for d in weekdays if d.weekday() < 5 and not is_trading_day(d)]
    assert closed == HOLIDAYS_2026


@pytest.mark.parametrize("day", EARLY_CLOSES_2026, ids=str)
def test_early_close_day_is_trading_day_closing_at_13_et(day: date) -> None:
    current = session(day)
    assert current is not None
    assert to_et(current.close).hour == 13


# --- основная сессия ---


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (et(2026, 10, 13, 9, 29, 59), False),
        (et(2026, 10, 13, 9, 30), True),
        (et(2026, 10, 13, 12, 0), True),
        (et(2026, 10, 13, 15, 59, 59), True),
        (et(2026, 10, 13, 16, 0), False),
        (et(2026, 10, 13, 18, 0), False),  # after-hours
        (et(2026, 10, 13, 7, 0), False),  # pre-market
        (et(2026, 10, 17, 12, 0), False),  # суббота
        (et(2026, 11, 26, 12, 0), False),  # Thanksgiving
        (et(2026, 11, 27, 12, 59, 59), True),  # сокращённый день
        (et(2026, 11, 27, 13, 0), False),
        (et(2026, 12, 24, 13, 30), False),
    ],
    ids=lambda v: v.isoformat() if isinstance(v, datetime) else str(v),
)
def test_is_regular_session(moment: datetime, expected: bool) -> None:
    assert is_regular_session(moment) is expected


@pytest.mark.parametrize(
    ("moment_utc", "expected"),
    [
        # Пт 30.10.2026, ещё летнее время (EDT, UTC−4): 9:30 ET = 13:30 UTC.
        (datetime(2026, 10, 30, 13, 30, tzinfo=UTC), True),
        (datetime(2026, 10, 30, 19, 59, tzinfo=UTC), True),
        (datetime(2026, 10, 30, 20, 0, tzinfo=UTC), False),
        # Пн 02.11.2026, уже зимнее (EST, UTC−5): 9:30 ET = 14:30 UTC.
        (datetime(2026, 11, 2, 13, 30, tzinfo=UTC), False),
        (datetime(2026, 11, 2, 14, 29, tzinfo=UTC), False),
        (datetime(2026, 11, 2, 14, 30, tzinfo=UTC), True),
        (datetime(2026, 11, 2, 20, 59, tzinfo=UTC), True),
        (datetime(2026, 11, 2, 21, 0, tzinfo=UTC), False),
        # Пн 09.03.2026, после перехода на летнее: 9:30 ET = 13:30 UTC.
        (datetime(2026, 3, 9, 13, 30, tzinfo=UTC), True),
        (datetime(2026, 3, 6, 13, 30, tzinfo=UTC), False),  # пятница до перехода: 8:30 EST
    ],
    ids=lambda v: v.isoformat() if isinstance(v, datetime) else str(v),
)
def test_regular_session_across_daylight_saving_changes(
    moment_utc: datetime, expected: bool
) -> None:
    assert is_regular_session(moment_utc) is expected


def test_regular_session_in_moscow_time() -> None:
    # 17:30 МСК 02.11.2026 = 9:30 EST — открытие.
    assert is_regular_session(datetime(2026, 11, 2, 17, 30, tzinfo=MSK))
    assert not is_regular_session(datetime(2026, 11, 2, 16, 30, tzinfo=MSK))


# --- следующее открытие ---


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (et(2026, 10, 13, 8, 0), et(2026, 10, 13, 9, 30)),  # до открытия — сегодня
        (et(2026, 10, 13, 9, 30), et(2026, 10, 14, 9, 30)),  # ровно открытие — следующее
        (et(2026, 10, 13, 11, 0), et(2026, 10, 14, 9, 30)),  # в сессии — завтра
        (et(2026, 10, 16, 17, 0), et(2026, 10, 19, 9, 30)),  # пятница вечер — понедельник
        (et(2026, 11, 25, 17, 0), et(2026, 11, 27, 9, 30)),  # через Thanksgiving
        (et(2026, 10, 30, 17, 0), et(2026, 11, 2, 9, 30)),  # через переход на зимнее время
        (et(2026, 12, 31, 17, 0), et(2027, 1, 4, 9, 30)),  # через Новый год (1.01.2027 — пятница)
    ],
    ids=lambda v: v.isoformat(),
)
def test_next_session_open(moment: datetime, expected: datetime) -> None:
    assert next_session_open(moment) == expected


def test_next_session_open_is_utc_across_dst() -> None:
    assert next_session_open(et(2026, 10, 30, 17, 0)) == datetime(2026, 11, 2, 14, 30, tzinfo=UTC)


# --- время ---


def test_et_to_msk_after_us_switch_to_standard_time() -> None:
    moment = et(2026, 11, 2, 9, 30)
    assert to_msk(moment).replace(tzinfo=None) == datetime(2026, 11, 2, 17, 30)  # noqa: DTZ001


def test_et_to_msk_before_us_switch() -> None:
    moment = et(2026, 10, 30, 9, 30)
    assert to_msk(moment).replace(tzinfo=None) == datetime(2026, 10, 30, 16, 30)  # noqa: DTZ001


def test_to_et_converts_utc() -> None:
    converted = to_et(datetime(2026, 11, 2, 14, 30, tzinfo=UTC))
    assert (converted.hour, converted.minute, converted.tzinfo) == (9, 30, ET)


NAIVE = datetime(2026, 10, 13, 9, 30)  # noqa: DTZ001 — the point of the test


@pytest.mark.parametrize("func", [is_regular_session, next_session_open, to_et, to_msk])
def test_naive_datetime_rejected(func: object) -> None:
    assert callable(func)
    with pytest.raises(ValueError, match="naive datetime"):
        func(NAIVE)


# --- недельная экспирация ---


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 10, 13), date(2026, 10, 16)),  # вторник → пятница той же недели
        (date(2026, 10, 16), date(2026, 10, 16)),  # пятница → та же пятница
        (date(2026, 10, 17), date(2026, 10, 23)),  # суббота → следующая пятница
        (date(2026, 3, 30), date(2026, 4, 2)),  # Good Friday 03.04 → четверг
        (date(2026, 4, 3), date(2026, 4, 10)),  # сама праздничная пятница → следующая неделя
        (date(2026, 6, 15), date(2026, 6, 18)),  # Juneteenth 19.06 → четверг
        (date(2026, 6, 29), date(2026, 7, 2)),  # 03.07 выходной → четверг
        (date(2026, 12, 21), date(2026, 12, 24)),  # Рождество 25.12 → сокращённый четверг
    ],
    ids=str,
)
def test_weekly_expiry(day: date, expected: date) -> None:
    assert weekly_expiry(day) == expected


# --- соседние торговые дни и день реакции ---


@pytest.mark.parametrize(
    ("day", "previous", "following"),
    [
        (date(2026, 10, 14), date(2026, 10, 13), date(2026, 10, 15)),  # среда
        (date(2026, 10, 19), date(2026, 10, 16), date(2026, 10, 20)),  # понедельник
        (date(2026, 10, 17), date(2026, 10, 16), date(2026, 10, 19)),  # суббота
        (date(2026, 11, 27), date(2026, 11, 25), date(2026, 11, 30)),  # после Thanksgiving
        (date(2027, 1, 4), date(2026, 12, 31), date(2027, 1, 5)),  # через Новый год
    ],
    ids=str,
)
def test_previous_and_next_trading_day(day: date, previous: date, following: date) -> None:
    assert previous_trading_day(day) == previous
    assert next_trading_day(day) == following


@pytest.mark.parametrize(
    ("day", "direction", "expected"),
    [
        (date(2026, 10, 14), "previous", date(2026, 10, 14)),  # торговый — без изменений
        (date(2026, 10, 14), "next", date(2026, 10, 14)),
        (date(2026, 10, 18), "previous", date(2026, 10, 16)),  # воскресенье → пятница
        (date(2026, 10, 18), "next", date(2026, 10, 19)),  # воскресенье → понедельник
        (date(2026, 11, 26), "previous", date(2026, 11, 25)),  # Thanksgiving
        (date(2026, 11, 26), "next", date(2026, 11, 27)),
    ],
    ids=str,
)
def test_shift_to_trading_day(day: date, direction: Any, expected: date) -> None:
    assert shift_to_trading_day(day, direction) == expected


@pytest.mark.parametrize(
    ("report_date", "report_time", "expected"),
    [
        (date(2026, 10, 13), "BMO", date(2026, 10, 13)),
        (date(2026, 10, 13), "DURING", date(2026, 10, 13)),
        (date(2026, 10, 13), None, date(2026, 10, 13)),  # время неизвестно — как BMO
        (date(2026, 10, 15), "AMC", date(2026, 10, 16)),
        (date(2026, 10, 16), "AMC", date(2026, 10, 19)),  # пятница → понедельник
        (date(2026, 11, 25), "AMC", date(2026, 11, 27)),  # через Thanksgiving
        (date(2026, 10, 17), "BMO", date(2026, 10, 19)),  # отчёт в субботу → понедельник
    ],
    ids=str,
)
def test_reaction_day(report_date: date, report_time: Any, expected: date) -> None:
    assert reaction_day(report_date, report_time) == expected
