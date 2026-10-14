"""Симуляция сделок на move_ratio (T12): вход по закрытию накануне, выход по минутам до 11:00 ET.

Правила SPEC §10 (числа — thresholds.yaml `constructions`):
- стрэддл (покупка): стоп — стоимость упала на stop_premium_loss, цель — выросла на
  target_premium_gain, иначе выход по цене в exit_time_et;
- iron condor (продажа): стоп по толкованию stop_basis — cost: выкуп стоит stop_premium_multiple ×
  премии, loss: убыток stop_premium_multiple × премии (выкуп (1 + N) ×); цель — выкуп за
  (1 − target_premium_share) × премии, иначе выход в exit_time_et.
Цена ноги — последняя сделка (минутные свечи редкие); стоимость позиции считается с минуты,
когда по всем ногам уже были сделки. Стоп и цель проверяются по цене закрытия минуты.

Издержки — только через CostModel (SPEC §17 п.3): вход и выход каждой ноги, один контракт.
"""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from backtest.signals import Construction
from core.config.thresholds import CondorStopBasis, Constructions
from core.domain.options import OptionMinuteBar
from execution.costs import CostLeg, CostModel, total_cost

CONTRACT_MULTIPLIER = 100
# stop / target / time — опционы (выход до 11:00); trail_stop / sma / max_hold — акция в режиме C.
ExitReason = Literal["stop", "target", "time", "trail_stop", "sma", "max_hold"]
TradeKind = Literal["straddle", "iron_condor", "mode_c"]
SkipReason = Literal["no_exit_price", "no_credit"]


@dataclass(frozen=True)
class Leg:
    ticker: str
    side: Literal[1, -1]  # 1 — купленная нога, −1 — проданная
    entry_price: float


@dataclass(frozen=True)
class Trade:
    ticker: str
    report_date: date
    construction: TradeKind
    entry_value: float  # стрэддл — уплаченная премия, кондор — полученная, на акцию
    exit_value: float  # стоимость позиции при выходе (для кондора — цена выкупа), на акцию
    exit_reason: ExitReason
    exit_at: datetime
    gross_pnl: float  # $, один контракт на ногу
    costs: float  # $, вход + выход
    risk: float  # $, максимальный убыток с издержками входа
    variant: str = ""  # у кондора — толкование стопа (cost / loss)
    entry_on: date | None = None  # день входа (уровень Black Swan — на закрытии дня до него)

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.costs

    @property
    def return_on_risk(self) -> float:
        return self.net_pnl / self.risk


def position_path(
    legs: Sequence[Leg], minutes: Mapping[str, Sequence[OptionMinuteBar]]
) -> list[tuple[datetime, float]]:
    """Стоимость позиции по минутам: Σ сторона × последняя цена ноги, когда цены есть у всех ног."""
    events = sorted(
        (bar.minute, leg.ticker, bar.close) for leg in legs for bar in minutes.get(leg.ticker, [])
    )
    last: dict[str, float] = {}
    path: list[tuple[datetime, float]] = []
    for moment, ticker, close in events:
        last[ticker] = close
        if len(last) == len(legs):
            value = sum(leg.side * last[leg.ticker] for leg in legs)
            if path and path[-1][0] == moment:
                path[-1] = (moment, value)
            else:
                path.append((moment, value))
    return path


def simulate(
    ticker: str,
    report_date: date,
    construction: Construction,
    legs: Sequence[Leg],
    minutes: Mapping[str, Sequence[OptionMinuteBar]],
    *,
    rules: Constructions,
    costs: CostModel,
    session_open: datetime,
    open_slippage_minutes: int,
    width: float | None = None,
    condor_stop: CondorStopBasis | None = None,
    entry_on: date | None = None,
) -> Trade | SkipReason:
    """Одна сделка: вход по ценам ног накануне, выход по первому правилу из стоп / цель / время."""
    entry = sum(leg.side * leg.entry_price for leg in legs)  # стрэддл > 0, кондор < 0
    path = position_path(legs, minutes)
    if not path:
        return "no_exit_price"
    max_loss: float
    basis: CondorStopBasis | None = None
    if construction == "straddle":
        premium = entry
        straddle = rules.straddle
        stop = premium * (1 - straddle.stop_premium_loss)
        target = premium * (1 + straddle.target_premium_gain)
        moment, value, reason = _first(path, lambda v: v <= stop, lambda v: v >= target)
        gross = (value - premium) * CONTRACT_MULTIPLIER
        exit_value = value
        max_loss = premium * CONTRACT_MULTIPLIER
    else:
        credit = -entry
        if credit <= 0 or width is None:
            return "no_credit"
        condor = rules.iron_condor
        basis = condor_stop or condor.stop_basis
        multiple = condor.stop_premium_multiple
        stop = credit * (multiple if basis == "cost" else 1 + multiple)
        target = credit * (1 - condor.target_premium_share)
        # Для кондора путь — Σ сторона × цена < 0; выкуп стоит −путь.
        moment, value, reason = _first(path, lambda v: -v >= stop, lambda v: -v <= target)
        exit_value = -value
        gross = (credit - exit_value) * CONTRACT_MULTIPLIER
        premium = credit
        max_loss = (width - credit) * CONTRACT_MULTIPLIER
    at_open = moment < session_open + timedelta(minutes=open_slippage_minutes)
    exit_prices = _exit_prices(legs, minutes, moment)
    entry_prices = {leg.ticker: leg.entry_price for leg in legs}
    entry_costs = total_cost(costs, _cost_legs(legs, entry_prices), at_open=False)
    exit_costs = total_cost(costs, _cost_legs(legs, exit_prices), at_open=at_open)
    return Trade(
        ticker=ticker,
        report_date=report_date,
        construction=construction,
        entry_value=premium,
        exit_value=exit_value,
        exit_reason=reason,
        exit_at=moment,
        gross_pnl=gross,
        costs=entry_costs.total + exit_costs.total,
        risk=max_loss + entry_costs.total,
        variant=basis or "",
        entry_on=entry_on,
    )


def _first(
    path: Sequence[tuple[datetime, float]],
    is_stop: Callable[[float], bool],
    is_target: Callable[[float], bool],
) -> tuple[datetime, float, ExitReason]:
    for moment, value in path:
        if is_stop(value):
            return moment, value, "stop"
        if is_target(value):
            return moment, value, "target"
    moment, value = path[-1]
    return moment, value, "time"


def _exit_prices(
    legs: Sequence[Leg], minutes: Mapping[str, Sequence[OptionMinuteBar]], moment: datetime
) -> dict[str, float]:
    prices = {}
    for leg in legs:
        before = [b for b in minutes[leg.ticker] if b.minute <= moment]
        prices[leg.ticker] = before[-1].close
    return prices


def _cost_legs(legs: Sequence[Leg], prices: Mapping[str, float]) -> list[CostLeg]:
    return [
        CostLeg(
            instrument="option",
            quantity=1,
            multiplier=CONTRACT_MULTIPLIER,
            price=prices[leg.ticker],
        )
        for leg in legs
    ]
