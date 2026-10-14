"""Агент «Позиционирование» (SPEC §8): pre_run_30d, pre_run_3d, volume_anomaly, short_interest_days.

Всё — на закрытии торгового дня перед запуском (задачи T−7 07:30, T−3 и T−1 14:50 — до закрытия,
неполный день не берём). Короткие позиции — последний расчёт FINRA, который к этому моменту уже
опубликован (расчёт не позже short_interest_lag_days до запуска).
"""

import statistics
from collections.abc import Sequence
from datetime import timedelta
from typing import Protocol

from pydantic import BaseModel

from adapters.errors import DataError
from adapters.massive.models import ShortInterest
from adapters.massive.symbols import StockHistorySource, daily_bars
from core.config.thresholds import PositioningAgent
from core.registry.protocols import EventContext, Trigger
from core.session_guard import to_et

STAGES = ("T-7", "T-3", "T-1")


class PositioningSource(StockHistorySource, Protocol):
    def short_interest(self, ticker: str, limit: int = 10) -> list[ShortInterest]:
        """Расчёты коротких позиций, от новых к старым."""


class PositioningFeatures(BaseModel):
    pre_run_30d: float | None = None
    pre_run_3d: float | None = None
    volume_anomaly: float | None = None
    short_interest_days: float | None = None


class PositioningAgentPlugin:
    id = "positioning"
    version = "0.1.0"
    triggers: Sequence[Trigger] = tuple(Trigger("stage", s) for s in STAGES)
    reads: Sequence[str] = ("massive:daily_bars", "massive:short_interest")
    output_schema = PositioningFeatures

    def __init__(self, stocks: PositioningSource, settings: PositioningAgent) -> None:
        self._stocks = stocks
        self._settings = settings

    def run(self, ctx: EventContext) -> PositioningFeatures:
        day = to_et(ctx.as_of).date()
        s = self._settings
        start = day - timedelta(days=s.long_run_days + s.volume_lookback_days * 2)
        bars = [
            b
            for b in daily_bars(self._stocks, ctx.ticker, start, day)
            if to_et(b.start).date() < day
        ]
        if len(bars) <= max(s.short_run_trading_days, s.volume_lookback_days):
            raise DataError("massive", f"{ctx.ticker}: not enough daily bars before {day}")
        last = bars[-1]
        last_day = to_et(last.start).date()
        anchor = [
            b for b in bars if to_et(b.start).date() <= last_day - timedelta(days=s.long_run_days)
        ]
        previous = bars[-1 - s.volume_lookback_days : -1]
        average_volume = statistics.fmean(b.volume for b in previous)
        published = [
            r
            for r in self._stocks.short_interest(ctx.ticker)
            if r.settlement_date <= day - timedelta(days=s.short_interest_lag_days)
        ]
        latest = max(published, key=lambda r: r.settlement_date) if published else None
        return PositioningFeatures(
            pre_run_30d=last.close / anchor[-1].close - 1 if anchor else None,
            pre_run_3d=last.close / bars[-1 - s.short_run_trading_days].close - 1,
            volume_anomaly=last.volume / average_volume if average_volume > 0 else None,
            short_interest_days=None if latest is None else latest.days_to_cover,
        )
