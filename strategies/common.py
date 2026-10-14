"""Общие расчёты стратегий (T16): исторический ratio движения, цена и ATR акции, издержки.

Издержки — доля от максимального убытка конструкции (решение заказчика 15.10.2026): издержки входа
и выхода по CostModel брокера / максимальный убыток. Котировок нет — спреды из допущений
config/broker.yaml (опцион 3%, акция 0,05%), это видно в CostBreakdown.spread_assumed.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from adapters.massive.models import Bar
from adapters.massive.symbols import StockHistorySource, daily_bars
from backtest.mode_c import average_true_range
from core.db.store import earnings_history
from core.domain.types import ReportTime
from core.pricing.black_scholes import price
from core.session_guard import reaction_day, to_et, weekly_expiry
from execution.costs import CostLeg, CostModel, total_cost

OPTION_MULTIPLIER = 100
STOCK_SHARES = 100  # доля издержек не зависит от числа акций, кроме минимальной комиссии
HISTORY_DAYS = 60  # дневные свечи для цены и ATR(14)


@dataclass(frozen=True)
class StockState:
    """Акция на закрытии торгового дня перед решением."""

    day: date
    spot: float
    atr: float | None


def history_ratio(
    session: Session,
    ticker: str,
    report_date: date,
    implied_move: float,
    *,
    lookback: int,
    min_reports: int,
) -> float | None:
    """Средний |движение| последних lookback отчётов / implied move (как сигнал бэктеста T12)."""
    rows = [
        r
        for r in earnings_history(session, ticker, date.min)
        if r.report_date < report_date and r.date_check != "mismatch"
    ]
    moves = [abs(r.actual_move) for r in rows if r.actual_move is not None][-lookback:]
    if len(moves) < min_reports or implied_move <= 0:
        return None
    return (sum(moves) / len(moves)) / implied_move


def stock_state(
    source: StockHistorySource, ticker: str, day: date, atr_period: int
) -> StockState | None:
    """Цена закрытия и ATR на последнем торговом дне до day; нет свечей — None."""
    bars: Sequence[Bar] = [
        b
        for b in daily_bars(source, ticker, day - timedelta(days=HISTORY_DAYS), day)
        if to_et(b.start).date() < day
    ]
    if not bars or not bars[-1].close > 0:
        return None
    return StockState(
        day=to_et(bars[-1].start).date(),
        spot=bars[-1].close,
        atr=average_true_range(bars, atr_period),
    )


def years_to(day: date, expiration: date) -> float:
    """От закрытия дня решения до экспирации, в годах (не меньше одного дня)."""
    return max((expiration - day).days, 1) / 365


def front_expiration(report_date: date, report_time: ReportTime | None) -> date:
    """Экспирация опционов на отчёт: ближайшая пятница не раньше дня реакции (SPEC §10)."""
    return weekly_expiry(reaction_day(report_date, report_time))


def round_trip(model: CostModel, legs: Sequence[CostLeg]) -> float:
    """Издержки входа (по закрытию) и выхода (в первые минуты открытия — с проскальзыванием)."""
    return (
        total_cost(model, legs, at_open=False).total + total_cost(model, legs, at_open=True).total
    )


def option_leg(premium: float, contracts: int = 1) -> CostLeg:
    return CostLeg("option", contracts, OPTION_MULTIPLIER, premium)


def straddle_cost_fraction(model: CostModel, spot: float, implied_move: float) -> float | None:
    """Стрэддл: максимальный убыток — уплаченная премия ≈ implied move · цена."""
    premium = implied_move * spot
    if not premium > 0:
        return None
    legs = [option_leg(premium / 2), option_leg(premium / 2)]
    cost = round_trip(model, legs)
    return cost / (premium * OPTION_MULTIPLIER + total_cost(model, legs, at_open=False).total)


def condor_cost_fraction(
    model: CostModel,
    spot: float,
    implied_move: float,
    atm_iv: float,
    years: float,
    rate: float,
    short_moves: float,
    wing_moves: float,
) -> float | None:
    """Iron condor на ± short / wing implied move (страйки — теоретические, цены — Блэк–Шоулз).

    Максимальный убыток = ширина крыла − полученная премия. Нет премии — None.
    """
    strikes = {
        "sp": spot * (1 - short_moves * implied_move),
        "lp": spot * (1 - wing_moves * implied_move),
        "sc": spot * (1 + short_moves * implied_move),
        "lc": spot * (1 + wing_moves * implied_move),
    }
    put_short = price("put", spot, strikes["sp"], years, rate, atm_iv)
    put_long = price("put", spot, strikes["lp"], years, rate, atm_iv)
    call_short = price("call", spot, strikes["sc"], years, rate, atm_iv)
    call_long = price("call", spot, strikes["lc"], years, rate, atm_iv)
    credit = put_short + call_short - put_long - call_long
    width = max(strikes["lc"] - strikes["sc"], strikes["sp"] - strikes["lp"])
    max_loss = (width - credit) * OPTION_MULTIPLIER
    if not credit > 0 or not max_loss > 0:
        return None
    legs = [option_leg(p) for p in (put_short, put_long, call_short, call_long) if p > 0]
    return round_trip(model, legs) / max_loss


def stock_cost_fraction(model: CostModel, spot: float, stop_distance: float) -> float | None:
    """Акция со стопом: максимальный убыток — расстояние до стопа на акцию."""
    if not stop_distance > 0 or not math.isfinite(stop_distance):
        return None
    leg = CostLeg("stock", STOCK_SHARES, 1, spot)
    return round_trip(model, [leg]) / (stop_distance * STOCK_SHARES)


def collar_cost_fraction(
    model: CostModel,
    spot: float,
    atm_iv: float,
    years: float,
    rate: float,
    put_otm: float,
    call_otm: float,
) -> float | None:
    """Акция + коллар (купленный пут ≈ −5%, проданный колл ≈ +7–8%, SPEC §10).

    Максимальный убыток на акцию = цена − страйк пута + (цена пута − цена колла).
    """
    put_strike, call_strike = spot * (1 - put_otm), spot * (1 + call_otm)
    put_price = price("put", spot, put_strike, years, rate, atm_iv)
    call_price = price("call", spot, call_strike, years, rate, atm_iv)
    loss_per_share = spot - put_strike + put_price - call_price
    if not loss_per_share > 0:
        return None
    legs = [
        CostLeg("stock", STOCK_SHARES, 1, spot),
        option_leg(put_price),
        option_leg(call_price),
    ]
    return round_trip(model, legs) / (loss_per_share * STOCK_SHARES)


def put_spread_cost_fraction(
    model: CostModel, spot: float, atm_iv: float, years: float, rate: float, width: float
) -> float | None:
    """Медвежий вертикальный спред: пут у цены куплен, на width ниже продан; убыток — дебет."""
    long_put = price("put", spot, spot, years, rate, atm_iv)
    short_put = price("put", spot, spot * (1 - width), years, rate, atm_iv)
    debit = (long_put - short_put) * OPTION_MULTIPLIER
    if not debit > 0:
        return None
    return round_trip(model, [option_leg(long_put), option_leg(short_put)]) / debit
