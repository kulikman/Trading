"""Агент «Макро» (SPEC §8): vix, us10y, regime — на закрытии предыдущего торгового дня.

regime — уровень Black Swan 0–3 (зелёный … красный) по правилу risk_limits.black_swan.rule
(решение заказчика 14.10.2026). us10y — доля (4,25% → 0.0425).
"""

import logging
from collections.abc import Sequence
from datetime import date, timedelta

from pydantic import BaseModel

from adapters.cboe.client import VixSource
from adapters.errors import DataError
from adapters.fred.client import FredObservation, FredSource
from adapters.massive.history import stock_closes
from adapters.massive.symbols import StockHistorySource, daily_bars
from core.config.thresholds import BlackSwan, MacroAgent
from core.registry.protocols import EventContext, Trigger
from core.risk.black_swan import ORDER, levels
from core.session_guard import previous_trading_day, to_et

logger = logging.getLogger(__name__)

VIX_SERIES = "VIXCLS"
US10Y_SERIES = "DGS10"
STAGES = ("T-7", "T-3", "T-1")


class MacroFeatures(BaseModel):
    vix: float | None = None
    us10y: float | None = None
    regime: int | None = None  # 0 зелёный, 1 жёлтый, 2 оранжевый, 3 красный


class MacroAgentPlugin:
    id = "macro"
    version = "0.1.0"
    triggers: Sequence[Trigger] = tuple(Trigger("stage", s) for s in STAGES)
    reads: Sequence[str] = ("cboe:VIX", "fred:VIXCLS", "fred:DGS10", "massive:SPY")
    output_schema = MacroFeatures

    def __init__(
        self,
        fred: FredSource,
        stocks: StockHistorySource,
        black_swan: BlackSwan,
        settings: MacroAgent,
        vix: VixSource | None = None,
    ) -> None:
        self._vix = vix
        self._fred = fred
        self._stocks = stocks
        self._black_swan = black_swan
        self._settings = settings

    def run(self, ctx: EventContext) -> MacroFeatures:
        """Значения на закрытии торгового дня перед моментом запуска."""
        close_day = previous_trading_day(to_et(ctx.as_of).date())
        start = close_day - timedelta(days=self._settings.lookback_days)
        vix = vix_closes(self._fred, self._vix, start, close_day)
        rates = observed_values(self._fred.observations(US10Y_SERIES, start, close_day))
        spy = stock_closes(daily_bars(self._stocks, "SPY", start, close_day))
        by_day = levels(vix, spy, self._black_swan)
        level = by_day.get(close_day)
        return MacroFeatures(
            vix=_last(vix),
            us10y=None if (rate := _last(rates)) is None else rate / 100,
            regime=None if level is None else ORDER.index(level),
        )


def vix_closes(
    fred: FredSource, cboe: VixSource | None, start: date, end: date
) -> dict[date, float]:
    """Закрытия VIX: FRED, поверх — CBOE (без задержки FRED).

    Сбой одного источника не роняет задачу, пока работает другой; оба недоступны — DataError.
    """
    values: dict[date, float] = {}
    fred_error: DataError | None = None
    try:
        values = observed_values(fred.observations(VIX_SERIES, start, end))
    except DataError as exc:
        if cboe is None:
            raise
        fred_error = exc
        logger.warning("fred vix unavailable, using cboe", extra={"detail": exc.detail})
    if cboe is None:
        return values
    try:
        return values | cboe.vix_closes(start, end)
    except DataError as exc:
        if fred_error is not None:
            raise DataError(
                "macro", f"VIX: fred — {fred_error.detail}; cboe — {exc.detail}"
            ) from exc
        logger.warning("cboe vix unavailable, using fred", extra={"detail": exc.detail})
        return values


def observed_values(rows: list[FredObservation]) -> dict[date, float]:
    return {o.date: o.value for o in rows if o.value is not None}


def _last(values: dict[date, float]) -> float | None:
    return values[max(values)] if values else None
