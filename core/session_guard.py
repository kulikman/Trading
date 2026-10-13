"""Торговый календарь NYSE и проверка основной сессии (SPEC §1, §10, §13).

Ордера — только в основную сессию: 9:30 ET до закрытия (16:00 или 13:00 в сокращённый день).
Всё время на входе — с часовым поясом; наивный datetime — ошибка.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from functools import cache
from zoneinfo import ZoneInfo

import pandas_market_calendars as mcal

ET = ZoneInfo("America/New_York")
MSK = ZoneInfo("Europe/Moscow")
FRIDAY = 4
ONE_DAY = timedelta(days=1)


@dataclass(frozen=True)
class Session:
    """Основная сессия торгового дня; open и close — в UTC."""

    open: datetime
    close: datetime


@cache
def _year_schedule(year: int) -> dict[date, Session]:
    frame = mcal.get_calendar("NYSE").schedule(start_date=f"{year}-01-01", end_date=f"{year}-12-31")
    return {
        day.date(): Session(
            open=row.market_open.to_pydatetime(), close=row.market_close.to_pydatetime()
        )
        for day, row in frame.iterrows()
    }


def _require_aware(moment: datetime) -> None:
    if moment.tzinfo is None or moment.utcoffset() is None:
        raise ValueError(f"naive datetime is not allowed: {moment.isoformat()}")


def session(day: date) -> Session | None:
    """Основная сессия дня или None, если биржа закрыта."""
    return _year_schedule(day.year).get(day)


def is_trading_day(day: date) -> bool:
    """Торговый ли день на NYSE (выходные и праздники — нет, сокращённые дни — да)."""
    return session(day) is not None


def is_regular_session(moment: datetime) -> bool:
    """Открыта ли основная сессия в этот момент: [open, close)."""
    _require_aware(moment)
    current = session(to_et(moment).date())
    return current is not None and current.open <= moment < current.close


def next_session_open(moment: datetime) -> datetime:
    """Ближайшее открытие основной сессии строго после момента (UTC)."""
    _require_aware(moment)
    day = to_et(moment).date()
    while True:
        current = session(day)
        if current is not None and current.open > moment:
            return current.open
        day += ONE_DAY


def to_et(moment: datetime) -> datetime:
    """Момент в нью-йоркском времени (EDT / EST по дате)."""
    _require_aware(moment)
    return moment.astimezone(ET)


def to_msk(moment: datetime) -> datetime:
    """Момент в московском времени (UTC+3 круглый год)."""
    _require_aware(moment)
    return moment.astimezone(MSK)


def weekly_expiry(day: date) -> date:
    """Недельная экспирация для даты: ближайшая пятница не раньше `day`.

    Пятница — праздник → предыдущий торговый день (обычно четверг). Если такой день
    оказался раньше `day` (дата сама — праздничная пятница), берётся следующая неделя.
    """
    friday = day + timedelta(days=(FRIDAY - day.weekday()) % 7)
    expiry = friday
    while not is_trading_day(expiry):
        expiry -= ONE_DAY
    if expiry < day:
        return weekly_expiry(friday + ONE_DAY)
    return expiry
