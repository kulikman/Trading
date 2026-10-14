"""Исторический ATM-стрэддл на прошлых отчётах по ценам закрытия опционов (T10, SPEC §9).

Котировок за прошлое нет — берутся дневные цены сделок (close) колла и пута одного страйка
накануне реакции рынка. Implied move = стрэддл / цена акции, метод `close_based`.

Порядок: день реакции (BMO — день отчёта, AMC — следующий торговый) → накануне (последний
торговый день до реакции) → справочник контрактов на тот день → ближайшая экспирация не раньше
реакции → страйки по близости к цене → цены пары, пока обе ноги не торговались накануне.
"""

import logging
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal, Protocol

from adapters.errors import DataError
from adapters.massive.models import Bar, ContractType, OptionContract
from core.config.sources import MassiveHistory
from core.domain.options import OptionDailyBar
from core.domain.types import OptionType, ReportTime
from core.pricing.black_scholes import implied_volatility
from core.session_guard import ET, previous_trading_day, reaction_day, session, to_et

logger = logging.getLogger(__name__)

SOURCE = "massive"
SECONDS_PER_YEAR = 365 * 24 * 60 * 60
MARKET_CLOSE = time(16, 0)


class OptionHistorySource(Protocol):
    def option_contracts(
        self,
        underlying: str,
        *,
        contract_type: ContractType | None = None,
        expiration_gte: date | None = None,
        expiration_lte: date | None = None,
        as_of: date | None = None,
        expired: bool = False,
        strike_gte: float | None = None,
        strike_lte: float | None = None,
    ) -> list[OptionContract]:
        """Справочник контрактов."""

    def aggregates(
        self,
        ticker: str,
        multiplier: int,
        timespan: Literal["day"],
        start: date,
        end: date,
        *,
        adjusted: bool = True,
    ) -> list[Bar]:
        """Свечи за период."""


@dataclass(frozen=True)
class EventDays:
    report_date: date
    report_time: ReportTime | None
    reaction: date
    pre: date  # закрытие накануне реакции — момент оценки стрэддла

    @classmethod
    def of(cls, report_date: date, report_time: ReportTime | None) -> "EventDays":
        """Неизвестное время отчёта считается BMO (как в планировщике T09)."""
        reaction = reaction_day(report_date, report_time)
        return cls(report_date, report_time, reaction, previous_trading_day(reaction))


@dataclass(frozen=True)
class HistoricalStraddle:
    ticker: str
    days: EventDays
    expiration: date
    strike: float
    spot: float
    call_close: float
    put_close: float
    call_volume: float
    put_volume: float
    call_iv: float | None
    put_iv: float | None
    call_ticker: str
    put_ticker: str
    method: Literal["close_based"] = "close_based"

    @property
    def straddle(self) -> float:
        return self.call_close + self.put_close

    @property
    def move(self) -> float:
        """Ожидаемое движение, доля цены: 0.05 = ±5%."""
        return self.straddle / self.spot


def option_bars(contract: OptionContract, bars: Iterable[Bar]) -> list[OptionDailyBar]:
    """Свечи Massive → строки архива; день свечи — дата начала окна по ET."""
    option_type = _option_type(contract)
    return [
        OptionDailyBar(
            option_ticker=contract.ticker,
            day=to_et(bar.start).date(),
            underlying=contract.underlying_ticker,
            expiration=contract.expiration_date,
            strike=contract.strike_price,
            option_type=option_type,
            open=bar.open,
            high=bar.high,
            low=bar.low,
            close=bar.close,
            volume=bar.volume,
            vwap=bar.vwap,
            transactions=bar.transactions,
        )
        for bar in bars
    ]


def fetch_event_bars(
    source: OptionHistorySource,
    ticker: str,
    days: EventDays,
    spot: float,
    settings: MassiveHistory,
) -> list[OptionDailyBar]:
    """Цены контрактов вокруг отчёта: ATM-пара, а если она не торговалась накануне — следующая.

    Возвращает всё скачанное (для архива), даже если ни одна пара не подошла.
    """
    contracts = source.option_contracts(
        ticker,
        expiration_gte=days.reaction,
        expiration_lte=days.reaction + timedelta(days=settings.expiration_lookahead_days),
        as_of=days.pre,  # контракты, торговавшиеся в тот день, в тогдашних страйках (до сплитов)
        strike_gte=spot * (1 - settings.strike_band),
        strike_lte=spot * (1 + settings.strike_band),
    )
    if not contracts:
        raise DataError(
            SOURCE, f"{ticker} {days.report_date}: no option contracts as of {days.pre}"
        )
    expiration = min(c.expiration_date for c in contracts)
    pairs = pairs_by_distance([c for c in contracts if c.expiration_date == expiration], spot)
    start = days.pre - timedelta(days=settings.days_before)
    end = days.reaction + timedelta(days=settings.days_after)
    fetched: list[OptionDailyBar] = []
    for call, put in pairs[: settings.max_strike_attempts]:
        call_bars = option_bars(call, source.aggregates(call.ticker, 1, "day", start, end))
        fetched += call_bars
        if not any(b.day == days.pre for b in call_bars):
            logger.info("call not traded before report", extra={"contract": call.ticker})
            continue
        put_bars = option_bars(put, source.aggregates(put.ticker, 1, "day", start, end))
        fetched += put_bars
        if any(b.day == days.pre for b in put_bars):
            break
        logger.info("put not traded before report", extra={"contract": put.ticker})
    return fetched


def straddle_from_bars(
    ticker: str,
    days: EventDays,
    spot: float,
    bars: Sequence[OptionDailyBar],
    rate: float,
) -> HistoricalStraddle:
    """Стрэддл на закрытии накануне: ближайшая экспирация не раньше реакции, страйк ближе к цене.

    Считается из архива — повторный расчёт не требует запросов. Нет пары, торговавшейся
    накануне, — DataError (не интерполируем и не берём цену другого дня).
    """
    on_pre = [
        b
        for b in bars
        if b.day == days.pre and b.underlying == ticker and b.expiration >= days.reaction
    ]
    if not on_pre:
        raise DataError(SOURCE, f"{ticker} {days.report_date}: no option traded on {days.pre}")
    expiration = min(b.expiration for b in on_pre)
    calls = {b.strike: b for b in on_pre if b.expiration == expiration and b.option_type == "call"}
    puts = {b.strike: b for b in on_pre if b.expiration == expiration and b.option_type == "put"}
    strikes = sorted(set(calls) & set(puts), key=lambda k: (abs(k - spot), k))
    if not strikes:
        raise DataError(
            SOURCE, f"{ticker} {days.report_date}: no strike with both legs traded on {days.pre}"
        )
    strike = strikes[0]
    call, put = calls[strike], puts[strike]
    years = years_to_expiration(days.pre, expiration)
    return HistoricalStraddle(
        ticker=ticker,
        days=days,
        expiration=expiration,
        strike=strike,
        spot=spot,
        call_close=call.close,
        put_close=put.close,
        call_volume=call.volume,
        put_volume=put.volume,
        call_iv=implied_volatility("call", call.close, spot, strike, years, rate),
        put_iv=implied_volatility("put", put.close, spot, strike, years, rate),
        call_ticker=call.option_ticker,
        put_ticker=put.option_ticker,
    )


def stock_closes(bars: Iterable[Bar]) -> dict[date, float]:
    """Закрытия акции по дням ET."""
    return {to_et(bar.start).date(): bar.close for bar in bars}


def spot_on(closes: Mapping[date, float], ticker: str, days: EventDays) -> float:
    """Цена акции на закрытии накануне реакции; нет — DataError."""
    spot = closes.get(days.pre)
    if spot is None or not math.isfinite(spot) or spot <= 0:
        raise DataError(SOURCE, f"{ticker}: no stock close on {days.pre}")
    return spot


def pairs_by_distance(
    contracts: Sequence[OptionContract], spot: float
) -> list[tuple[OptionContract, OptionContract]]:
    """Пары колл / пут одного страйка, от ближайшего к цене акции."""
    calls = {c.strike_price: c for c in contracts if c.contract_type == "call"}
    puts = {c.strike_price: c for c in contracts if c.contract_type == "put"}
    strikes = sorted(set(calls) & set(puts), key=lambda k: (abs(k - spot), k))
    return [(calls[k], puts[k]) for k in strikes]


def _option_type(contract: OptionContract) -> OptionType:
    if contract.contract_type == "call":
        return "call"
    if contract.contract_type == "put":
        return "put"
    raise DataError(
        SOURCE, f"{contract.ticker}: unsupported contract type {contract.contract_type}"
    )


def years_to_expiration(pre: date, expiration: date) -> float:
    """В годах: от закрытия дня pre до закрытия в день экспирации (с учётом сокращённых сессий)."""
    return (_close(expiration) - _close(pre)).total_seconds() / SECONDS_PER_YEAR


def _close(day: date) -> datetime:
    trading = session(day)
    return trading.close if trading is not None else datetime.combine(day, MARKET_CLOSE, tzinfo=ET)
