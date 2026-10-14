"""Сигналы стратегий на move_ratio (T12, решения заказчика 14.10.2026).

Исторический ratio = средний |движение| последних N отчётов компании / implied move текущего.
Только отчёты до текущего — без заглядывания в будущее; отчёты с датой под сомнением
(`date_check = mismatch`) не используются ни как событие, ни как история.

> straddle.min_move_ratio — покупка стрэддла; < iron_condor.max_move_ratio — продажа iron condor.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal

from adapters.massive.history import EventDays
from core.config.thresholds import Backtest, Constructions
from core.domain.earnings import EarningsTrack

Construction = Literal["straddle", "iron_condor"]
NoSignal = Literal["no_history", "neutral"]


@dataclass(frozen=True)
class Signal:
    ticker: str
    days: EventDays
    implied_move: float
    history_move: float | None  # средний |движение| прошлых отчётов
    history_reports: int
    construction: Construction | None
    reason: NoSignal | None = None

    @property
    def ratio(self) -> float | None:
        return None if self.history_move is None else self.history_move / self.implied_move


@dataclass(frozen=True)
class CondorStrikes:
    long_put: float
    short_put: float
    short_call: float
    long_call: float

    @property
    def width(self) -> float:
        """Ширина крыла (наибольшая из двух) — для максимального убытка."""
        return max(self.long_call - self.short_call, self.short_put - self.long_put)


def signals(
    ticker: str,
    rows: Sequence[EarningsTrack],
    *,
    since: date,
    today: date,
    settings: Backtest,
    constructions: Constructions,
) -> list[Signal]:
    """Сигнал для каждого отчёта в окне опционов [since, today) с implied move."""
    usable = [r for r in rows if r.date_check != "mismatch"]
    result = []
    for row in usable:
        days = EventDays.of(row.report_date, row.report_time)
        if row.report_date < since or days.reaction >= today or not row.implied_move:
            continue
        past = [
            abs(r.actual_move)
            for r in usable
            if r.report_date < row.report_date and r.actual_move is not None
        ][-settings.signal_lookback_reports :]
        if len(past) < settings.signal_min_reports:
            result.append(
                Signal(ticker, days, row.implied_move, None, len(past), None, "no_history")
            )
            continue
        history = sum(past) / len(past)
        ratio = history / row.implied_move
        construction: Construction | None = None
        if ratio > constructions.straddle.min_move_ratio:
            construction = "straddle"
        elif ratio < constructions.iron_condor.max_move_ratio:
            construction = "iron_condor"
        result.append(
            Signal(
                ticker,
                days,
                row.implied_move,
                history,
                len(past),
                construction,
                None if construction else "neutral",
            )
        )
    return result


def condor_strikes(
    call_strikes: Sequence[float],
    put_strikes: Sequence[float],
    spot: float,
    implied_move: float,
    short_moves: float,
    wing_moves: float,
) -> CondorStrikes | None:
    """Ближайшие существующие страйки к цене ± short / wing implied move.

    Короткие — по разные стороны от цены, длинные — дальше коротких. Нет такого набора — None.
    """
    short_call = _nearest(
        [k for k in call_strikes if k > spot], spot * (1 + short_moves * implied_move)
    )
    short_put = _nearest(
        [k for k in put_strikes if k < spot], spot * (1 - short_moves * implied_move)
    )
    if short_call is None or short_put is None:
        return None
    long_call = _nearest(
        [k for k in call_strikes if k > short_call], spot * (1 + wing_moves * implied_move)
    )
    long_put = _nearest(
        [k for k in put_strikes if k < short_put], spot * (1 - wing_moves * implied_move)
    )
    if long_call is None or long_put is None:
        return None
    return CondorStrikes(long_put, short_put, short_call, long_call)


def _nearest(strikes: Sequence[float], target: float) -> float | None:
    return min(strikes, key=lambda k: (abs(k - target), k)) if strikes else None
