"""Ожидаемое рынком движение на отчёте по ATM-стрэддлу (SPEC §8, §9).

Два способа, в порядке предпочтения:
- straddle_mid — середины котировок колла и пута (нужен тариф с котировками опционов);
- iv_approx — по IV тех же контрактов: стрэддл ≈ √(2/π) · S · σ · √T
  (тариф Options Starter, котировок нет).
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, Protocol

from adapters.errors import DataError
from adapters.massive.models import OptionQuote, OptionSnapshot
from core.domain.types import ReportTime
from core.session_guard import is_trading_day, session, to_et

SOURCE = "massive"
ONE_DAY = timedelta(days=1)
SECONDS_PER_YEAR = 365 * 24 * 60 * 60
ATM_STRADDLE_FACTOR = math.sqrt(2 / math.pi)  # ≈ 0.798: цена ATM-стрэддла ≈ 0.8 · S · σ · √T

ImpliedMoveMethod = Literal["straddle_mid", "iv_approx"]


class OptionChainSource(Protocol):
    def option_chain(
        self,
        underlying: str,
        *,
        expiration_gte: date | None = None,
        expiration_lte: date | None = None,
    ) -> list[OptionSnapshot]:
        """Снимки опционов базового актива с экспирацией в заданном окне."""


@dataclass(frozen=True)
class ImpliedMove:
    ticker: str
    reaction_day: date
    expiration: date
    strike: float
    underlying_price: float
    straddle: float
    move: float  # доля цены: 0.05 = ±5%
    method: ImpliedMoveMethod


def reaction_day(report_date: date, report_time: ReportTime) -> date:
    """День реакции цены: BMO / DURING — день отчёта, AMC — следующий торговый день."""
    if report_time != "AMC":
        return report_date
    day = report_date + ONE_DAY
    while not is_trading_day(day):
        day += ONE_DAY
    return day


def implied_move(
    source: OptionChainSource,
    ticker: str,
    report_date: date,
    report_time: ReportTime,
    *,
    as_of: datetime,
    lookahead_days: int,
    max_plausible_iv: float,
) -> ImpliedMove:
    """Ожидаемое движение на ближайшей экспирации не раньше дня реакции, страйк — ближайший к цене.

    Нет цены, экспирации, ни котировок, ни IV — DataError: система не угадывает.
    """
    to_et(as_of)  # наивное время — ошибка
    reaction = reaction_day(report_date, report_time)
    chain = source.option_chain(
        ticker, expiration_gte=reaction, expiration_lte=reaction + timedelta(days=lookahead_days)
    )
    if not chain:
        raise DataError(
            SOURCE, f"{ticker}: no option expirations within {lookahead_days} days of {reaction}"
        )
    expiration = min(c.details.expiration_date for c in chain)
    contracts = [c for c in chain if c.details.expiration_date == expiration]
    price = _underlying_price(ticker, contracts)
    strike, call, put = _atm_pair(ticker, contracts, price)

    method: ImpliedMoveMethod
    quoted = _quoted_straddle(call, put)
    if quoted is not None:
        straddle, method = quoted, "straddle_mid"
    else:
        sigma = _atm_iv(ticker, call, put, max_plausible_iv)
        years = _years_to_expiry(ticker, expiration, as_of)
        straddle, method = ATM_STRADDLE_FACTOR * price * sigma * math.sqrt(years), "iv_approx"
    return ImpliedMove(
        ticker=ticker,
        reaction_day=reaction,
        expiration=expiration,
        strike=strike,
        underlying_price=price,
        straddle=straddle,
        move=straddle / price,
        method=method,
    )


def _underlying_price(ticker: str, contracts: Sequence[OptionSnapshot]) -> float:
    for contract in contracts:
        asset = contract.underlying_asset
        if asset is not None and asset.price is not None and asset.price > 0:
            return asset.price
    raise DataError(SOURCE, f"{ticker}: no underlying price in option chain (stocks plan?)")


def _atm_pair(
    ticker: str, contracts: Sequence[OptionSnapshot], price: float
) -> tuple[float, OptionSnapshot, OptionSnapshot]:
    calls = {c.details.strike_price: c for c in contracts if c.details.contract_type == "call"}
    puts = {c.details.strike_price: c for c in contracts if c.details.contract_type == "put"}
    strikes = sorted(set(calls) & set(puts), key=lambda strike: (abs(strike - price), strike))
    if not strikes:
        raise DataError(SOURCE, f"{ticker}: no strike with both a call and a put")
    strike = strikes[0]
    return strike, calls[strike], puts[strike]


def _quoted_straddle(call: OptionSnapshot, put: OptionSnapshot) -> float | None:
    call_mid, put_mid = _mid(call.last_quote), _mid(put.last_quote)
    if call_mid is None or put_mid is None:
        return None
    return call_mid + put_mid


def _mid(quote: OptionQuote | None) -> float | None:
    if quote is None or quote.bid <= 0 or quote.ask < quote.bid:
        return None
    return quote.midpoint if quote.midpoint is not None else (quote.bid + quote.ask) / 2


def _atm_iv(
    ticker: str, call: OptionSnapshot, put: OptionSnapshot, max_plausible_iv: float
) -> float:
    ivs = [call.implied_volatility, put.implied_volatility]
    usable = [iv for iv in ivs if iv is not None and iv > 0]
    if len(usable) != len(ivs):
        raise DataError(SOURCE, f"{ticker}: ATM strike has neither usable quotes nor IV")
    sigma = sum(usable) / len(usable)
    if sigma > max_plausible_iv:
        raise DataError(SOURCE, f"{ticker}: implausible IV {sigma} (percent instead of fraction?)")
    return sigma


def _years_to_expiry(ticker: str, expiration: date, as_of: datetime) -> float:
    expiry_session = session(expiration)
    if expiry_session is None:
        raise DataError(SOURCE, f"{ticker}: expiration {expiration} is not a trading day")
    seconds = (expiry_session.close - as_of).total_seconds()
    if seconds <= 0:
        raise DataError(SOURCE, f"{ticker}: expiration {expiration} has already closed")
    return seconds / SECONDS_PER_YEAR
