"""Ликвидность опционов компаний по архиву (E6, OPEN_QUESTIONS «ликвидность у 50 компаний»).

Архив хранит пару ATM-опционов накануне каждого прошлого отчёта: медиана их суммарного дневного
объёма за последние `recent` отчётов — мера ликвидности; недельные экспирации есть, если среди
экспираций архива есть пятницы не третьей недели месяца. Флаг `company.options_liquid` —
только для профиля компании, не фильтр сигналов (решение заказчика 15.10.2026: триггеры не режут).
Котировок (спред < 5%, SPEC §10) на тарифе нет — поэтому объём, а не спред.
"""

import statistics
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.db import models as orm

RECENT_DAYS = 8


@dataclass(frozen=True)
class Liquidity:
    ticker: str
    median_volume: float | None
    has_weeklies: bool
    days: int


def option_liquidity(session: Session, ticker: str, recent: int = RECENT_DAYS) -> Liquidity:
    """Медианный объём ATM-пары по последним дням архива и наличие недельных экспираций."""
    daily = session.execute(
        select(orm.OptionDailyBar.day, func.sum(orm.OptionDailyBar.volume))
        .where(orm.OptionDailyBar.underlying == ticker)
        .group_by(orm.OptionDailyBar.day)
        .order_by(orm.OptionDailyBar.day.desc())
        .limit(recent)
    ).all()
    expirations = session.scalars(
        select(orm.OptionDailyBar.expiration)
        .where(orm.OptionDailyBar.underlying == ticker)
        .distinct()
    ).all()
    weeklies = any(e.weekday() == 4 and not 15 <= e.day <= 21 for e in expirations)
    volumes = [float(v or 0) for _, v in daily]
    median = statistics.median(volumes) if volumes else None
    return Liquidity(ticker, median, weeklies, len(volumes))


def update_options_liquid(
    session: Session, tickers: list[str], min_volume: float
) -> list[Liquidity]:
    """Флаг ликвидности опционов у компаний вселенной; данных нет — флаг пустой (None)."""
    out = []
    for ticker in tickers:
        found = option_liquidity(session, ticker)
        company = session.get(orm.Company, ticker)
        if company is not None:
            company.options_liquid = (
                None
                if found.median_volume is None
                else found.median_volume >= min_volume and found.has_weeklies
            )
        out.append(found)
    session.flush()
    return out
