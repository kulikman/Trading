"""Ожидаемое рынком движение на отчёте по цене ATM-стрэддла (SPEC §8, §9)."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Protocol

from adapters.errors import DataError
from adapters.massive.models import OptionQuote, OptionSnapshot
from core.domain.types import ReportTime
from core.session_guard import is_trading_day

SOURCE = "massive"
ONE_DAY = timedelta(days=1)


class OptionChainSource(Protocol):
    def option_chain(
        self,
        underlying: str,
        *,
        expiration_gte: date | None = None,
        expiration_lte: date | None = None,
    ) -> list[OptionSnapshot]: ...


@dataclass(frozen=True)
class ImpliedMove:
    ticker: str
    reaction_day: date
    expiration: date
    strike: float
    underlying_price: float
    straddle: float
    move: float  # доля цены: 0.05 = ±5%


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
    lookahead_days: int,
) -> ImpliedMove:
    """(колл + пут на страйке, ближайшем к цене) / цена — на ближайшей экспирации ≥ дня реакции.

    Нет котировок, цены базового актива или экспирации в окне — DataError: система не угадывает.
    """
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
    straddle = _mid(ticker, call) + _mid(ticker, put)
    return ImpliedMove(
        ticker=ticker,
        reaction_day=reaction,
        expiration=expiration,
        strike=strike,
        underlying_price=price,
        straddle=straddle,
        move=straddle / price,
    )


def _underlying_price(ticker: str, contracts: Sequence[OptionSnapshot]) -> float:
    for contract in contracts:
        asset = contract.underlying_asset
        if asset is not None and asset.price is not None and asset.price > 0:
            return asset.price
    raise DataError(SOURCE, f"{ticker}: no underlying price in option chain (stocks plan?)")


def _atm_pair(
    ticker: str, contracts: Sequence[OptionSnapshot], price: float
) -> tuple[float, OptionQuote, OptionQuote]:
    calls = {
        c.details.strike_price: c.last_quote for c in contracts if c.details.contract_type == "call"
    }
    puts = {
        c.details.strike_price: c.last_quote for c in contracts if c.details.contract_type == "put"
    }
    strikes = sorted(set(calls) & set(puts), key=lambda strike: (abs(strike - price), strike))
    if not strikes:
        raise DataError(SOURCE, f"{ticker}: no strike with both a call and a put")
    strike = strikes[0]
    call, put = calls[strike], puts[strike]
    if call is None or put is None:
        raise DataError(
            SOURCE, f"{ticker}: no quotes for ATM strike {strike} (options quotes plan?)"
        )
    return strike, call, put


def _mid(ticker: str, quote: OptionQuote) -> float:
    if quote.bid <= 0 or quote.ask < quote.bid:
        raise DataError(SOURCE, f"{ticker}: unusable quote bid={quote.bid} ask={quote.ask}")
    return quote.midpoint if quote.midpoint is not None else (quote.bid + quote.ask) / 2
