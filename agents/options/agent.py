"""Агент «Опционы» (SPEC §8): implied_move, skew_25d, term_slope, iv_rank.

Основной путь — снимок цепочки Massive (Options Starter, подключён 15.10.2026): IV, дельта и цена
последней сделки каждого контракта на момент запуска (задержка 15 минут), цена акции — последняя
минутная свеча того же дня. Цепочка недоступна (тариф, сбой) или в ней нет ATM-пары — запасной путь
по дневным ценам контрактов на закрытии накануне, как архив и бэктест (T10, T12): IV — Блэк–Шоулз из
цены закрытия, ставка — FRED DGS3MO на тот же день.

- implied_move — ATM-стрэддл ближайшей экспирации не раньше дня реакции / цена акции;
- atm_iv — средняя IV колла и пута этого страйка;
- skew_25d — IV пута 25Δ − IV колла 25Δ той же экспирации (> 0 — путы дороже, рынок боится падения);
  по цепочке — контракты с дельтой ближе всего к ±0,25, по закрытиям — страйк этой дельты по ATM IV;
- term_slope — ATM IV ближней − ATM IV дальней (≥ ближней + term_back_min_days): премия за отчёт;
- iv_rank — доля прошлых отчётов компании, у которых ATM IV за столько же торговых дней до реакции
  была ниже текущей (решение заказчика 14.10.2026: сравнение с той же стадией прошлых отчётов,
  а не со всеми днями года); прошлые цены — из архива option_daily_bar (IV по закрытию).

Цены контрактов, скачанные запасным путём, сохраняются в архив — история для iv_rank и бэктеста.
"""

import logging
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from math import exp, isfinite, sqrt
from statistics import NormalDist
from typing import Literal, Protocol

from pydantic import BaseModel
from sqlalchemy.orm import Session

from adapters.errors import DataError
from adapters.fred.client import FredSource
from adapters.massive.history import (
    OptionHistorySource,
    option_bars,
    pairs_by_distance,
    stock_closes,
    years_to_expiration,
)
from adapters.massive.models import Bar, OptionContract, OptionSnapshot
from adapters.massive.symbols import StockHistorySource, daily_bars
from core.config.sources import MassiveHistory
from core.config.thresholds import OptionsAgent
from core.db.store import earnings_history, option_bars_on, save_option_bars
from core.domain.options import OptionDailyBar
from core.domain.types import OptionType
from core.pricing.black_scholes import implied_volatility
from core.registry.protocols import EventContext, Trigger
from core.session_guard import previous_trading_day, reaction_day, to_et

logger = logging.getLogger(__name__)

SOURCE = "massive"
RATE_SERIES = "DGS3MO"
STAGES = ("T-7", "T-3", "T-1")
BAR_LOOKBACK_DAYS = 7  # цены контракта за неделю до дня оценки — один запрос


class OptionsSource(OptionHistorySource, StockHistorySource, Protocol):
    """Снимок цепочки, справочник контрактов, свечи контрактов и акции, история тикера."""

    def option_chain(
        self,
        underlying: str,
        *,
        expiration_gte: date | None = None,
        expiration_lte: date | None = None,
        strike_gte: float | None = None,
        strike_lte: float | None = None,
    ) -> list[OptionSnapshot]:
        """Снимок цепочки: IV, греки, цена последней сделки."""

    def aggregates(
        self,
        ticker: str,
        multiplier: int,
        timespan: Literal["day", "minute"],
        start: date,
        end: date,
        *,
        adjusted: bool = True,
    ) -> list[Bar]:
        """Свечи: дневные — акции и контракты, минутные — цена акции на момент запуска."""


class OptionsFeatures(BaseModel):
    implied_move: float | None = None
    atm_iv: float | None = None
    skew_25d: float | None = None
    term_slope: float | None = None
    iv_rank: float | None = None
    iv_rank_reports: int = 0


@dataclass(frozen=True)
class ChainOption:
    """Контракт снимка с ценой последней сделки и IV."""

    kind: OptionType
    strike: float
    expiration: date
    close: float
    iv: float
    delta: float | None

    @classmethod
    def of(cls, row: OptionSnapshot) -> "ChainOption | None":
        """None — контракт без сделки или без IV (по нему нельзя посчитать признаки)."""
        close = row.day.close if row.day is not None else None
        iv = row.implied_volatility
        if close is None or close <= 0 or iv is None or not isfinite(iv) or iv <= 0:
            return None
        return cls(
            "call" if row.details.contract_type == "call" else "put",
            row.details.strike_price,
            row.details.expiration_date,
            close,
            iv,
            row.greeks.delta if row.greeks is not None else None,
        )


@dataclass(frozen=True)
class Market:
    """Цена акции и ставка на день оценки."""

    day: date
    spot: float
    rate: float


class OptionsAgentPlugin:
    id = "options"
    version = "0.1.0"
    triggers: Sequence[Trigger] = tuple(Trigger("stage", s) for s in STAGES)
    reads: Sequence[str] = (
        "massive:option_chain",
        "massive:stock_minute_bars",
        "massive:option_contracts",
        "massive:option_daily_bars",
        "fred:DGS3MO",
        "archive:option_daily_bar",
    )
    output_schema = OptionsFeatures

    def __init__(
        self,
        source: OptionsSource,
        fred: FredSource,
        history: MassiveHistory,
        settings: OptionsAgent,
    ) -> None:
        self._source = source
        self._fred = fred
        self._history = history
        self._settings = settings

    def run(self, ctx: EventContext) -> OptionsFeatures:
        if ctx.session is None:
            raise DataError("archive", "options agent needs the archive session")
        today = to_et(ctx.as_of).date()
        reaction = reaction_day(ctx.report_date, ctx.report_time)
        chain = self._chain(ctx.ticker, reaction, today, ctx.as_of) if today < reaction else None
        day = today if chain is not None else previous_trading_day(today)
        if day >= reaction:
            raise DataError(SOURCE, f"{ctx.ticker}: close {day} is not before reaction {reaction}")
        close_day = previous_trading_day(today)
        start = close_day - timedelta(days=self._settings.history_days)
        closes = stock_closes(daily_bars(self._source, ctx.ticker, start, close_day))
        rates = _rates(self._fred, start, close_day)
        if chain is not None:
            features = chain
        else:
            market = Market(day, _spot(closes, ctx.ticker, day), self._rate(rates, day))
            fetched: list[OptionDailyBar] = []
            try:
                features = self._live(ctx.ticker, reaction, market, fetched)
            finally:
                save_option_bars(ctx.session, fetched)
        past = self._past_ivs(ctx.session, ctx, day, reaction, closes, rates)
        current = features.atm_iv
        if current is not None and len(past) >= self._settings.iv_rank_min_reports:
            features.iv_rank = sum(v < current for v in past) / len(past)
        features.iv_rank_reports = len(past)
        return features

    def _chain(
        self, ticker: str, reaction: date, day: date, as_of: datetime
    ) -> OptionsFeatures | None:
        """Признаки по снимку цепочки; None — цепочки нет или в ней нет ATM-пары."""
        s, h = self._settings, self._history
        try:
            spot = _intraday_spot(self._source, ticker, day, as_of)
            rows = self._source.option_chain(
                ticker,
                expiration_gte=reaction,
                expiration_lte=reaction
                + timedelta(
                    days=h.expiration_lookahead_days
                    + s.term_back_min_days
                    + s.term_back_window_days
                ),
                strike_gte=spot * (1 - h.strike_band),
                strike_lte=spot * (1 + h.strike_band),
            )
        except DataError as exc:
            logger.warning(
                "options chain unavailable, falling back to daily closes",
                extra={"ticker": ticker, "detail": exc.detail},
            )
            return None
        options = [o for o in map(ChainOption.of, rows) if o is not None]
        near = [
            o
            for o in options
            if o.expiration <= reaction + timedelta(days=h.expiration_lookahead_days)
        ]
        front_expiration = min((o.expiration for o in near), default=None)
        front = [o for o in near if o.expiration == front_expiration]
        pair = _chain_atm(front, spot)
        if pair is None:
            logger.warning(
                "options chain has no ATM pair, falling back to daily closes",
                extra={"ticker": ticker, "contracts": len(rows)},
            )
            return None
        call, put = pair
        atm_iv = (call.iv + put.iv) / 2
        features = OptionsFeatures(implied_move=(call.close + put.close) / spot, atm_iv=atm_iv)
        features.skew_25d = _chain_skew(front, s.skew_delta)
        back_from = call.expiration + timedelta(days=s.term_back_min_days)
        back_expiration = min(
            (o.expiration for o in options if o.expiration >= back_from), default=None
        )
        back = _chain_atm([o for o in options if o.expiration == back_expiration], spot)
        if back is not None:
            features.term_slope = atm_iv - (back[0].iv + back[1].iv) / 2
        return features

    def _live(
        self, ticker: str, reaction: date, market: Market, fetched: list[OptionDailyBar]
    ) -> OptionsFeatures:
        s, h = self._settings, self._history
        last = reaction + timedelta(
            days=h.expiration_lookahead_days + s.term_back_min_days + s.term_back_window_days
        )
        contracts = self._source.option_contracts(
            ticker,
            expiration_gte=reaction,
            expiration_lte=last,
            as_of=market.day,
            strike_gte=market.spot * (1 - h.strike_band),
            strike_lte=market.spot * (1 + h.strike_band),
        )
        near = [
            c
            for c in contracts
            if c.expiration_date <= reaction + timedelta(days=h.expiration_lookahead_days)
        ]
        if not near:
            raise DataError(
                SOURCE, f"{ticker}: no option contracts after {reaction} on {market.day}"
            )
        front_expiration = min(c.expiration_date for c in near)
        front = [c for c in near if c.expiration_date == front_expiration]
        call, put = self._atm(ticker, front, market, fetched)
        atm_iv = _mean_iv(call, put, market)
        features = OptionsFeatures(
            implied_move=(call.close + put.close) / market.spot, atm_iv=atm_iv
        )
        if atm_iv is None:
            return features
        features.skew_25d = self._skew(front, atm_iv, market, fetched)
        back_from = front_expiration + timedelta(days=s.term_back_min_days)
        back = [c for c in contracts if c.expiration_date >= back_from]
        if back:
            back_expiration = min(c.expiration_date for c in back)
            pair = self._atm_or_none(
                [c for c in back if c.expiration_date == back_expiration], market, fetched
            )
            back_iv = None if pair is None else _mean_iv(*pair, market)
            if back_iv is not None:
                features.term_slope = atm_iv - back_iv
        return features

    def _atm(
        self,
        ticker: str,
        contracts: Sequence[OptionContract],
        market: Market,
        fetched: list[OptionDailyBar],
    ) -> tuple[OptionDailyBar, OptionDailyBar]:
        pair = self._atm_or_none(contracts, market, fetched)
        if pair is None:
            raise DataError(SOURCE, f"{ticker}: no ATM pair traded on {market.day}")
        return pair

    def _atm_or_none(
        self, contracts: Sequence[OptionContract], market: Market, fetched: list[OptionDailyBar]
    ) -> tuple[OptionDailyBar, OptionDailyBar] | None:
        """Ближайший к цене страйк, где обе ноги торговались в день оценки (не больше N попыток)."""
        for call, put in pairs_by_distance(contracts, market.spot)[
            : self._history.max_strike_attempts
        ]:
            call_bar = self._traded(call, market.day, fetched)
            if call_bar is None:
                continue
            put_bar = self._traded(put, market.day, fetched)
            if put_bar is not None:
                return call_bar, put_bar
        return None

    def _skew(
        self,
        contracts: Sequence[OptionContract],
        atm_iv: float,
        market: Market,
        fetched: list[OptionDailyBar],
    ) -> float | None:
        expiration = contracts[0].expiration_date
        years = years_to_expiration(market.day, expiration)
        delta = self._settings.skew_delta
        put_iv = self._iv_near(
            contracts, "put", _strike_for_delta(1 - delta, atm_iv, years, market), market, fetched
        )
        call_iv = self._iv_near(
            contracts, "call", _strike_for_delta(delta, atm_iv, years, market), market, fetched
        )
        return None if put_iv is None or call_iv is None else put_iv - call_iv

    def _iv_near(
        self,
        contracts: Sequence[OptionContract],
        kind: OptionType,
        target: float,
        market: Market,
        fetched: list[OptionDailyBar],
    ) -> float | None:
        """IV ближайшего к target страйка, торговавшегося в день оценки."""
        candidates = sorted(
            (c for c in contracts if c.contract_type == kind),
            key=lambda c: (abs(c.strike_price - target), c.strike_price),
        )
        for contract in candidates[: self._history.max_strike_attempts]:
            bar = self._traded(contract, market.day, fetched)
            if bar is not None:
                return _iv(bar, market)
        return None

    def _traded(
        self, contract: OptionContract, day: date, fetched: list[OptionDailyBar]
    ) -> OptionDailyBar | None:
        bars = option_bars(
            contract,
            self._source.aggregates(
                contract.ticker, 1, "day", day - timedelta(days=BAR_LOOKBACK_DAYS), day
            ),
        )
        fetched += bars
        return next((b for b in bars if b.day == day and b.close > 0), None)

    def _past_ivs(
        self,
        session: Session,
        ctx: EventContext,
        day: date,
        reaction: date,
        closes: Mapping[date, float],
        rates: Mapping[date, float],
    ) -> list[float]:
        """ATM IV прошлых отчётов за столько же торговых дней до реакции, что и сейчас."""
        lead = _trading_days_between(day, reaction)
        since = min(closes) if closes else reaction
        past = [
            r
            for r in earnings_history(session, ctx.ticker, since)
            if r.report_date < ctx.report_date
            and r.date_check != "mismatch"
            and reaction_day(r.report_date, r.report_time) <= day  # без заглядывания вперёд
        ]
        ivs: list[float] = []
        for report in reversed(past):
            if len(ivs) >= self._settings.iv_rank_reports:
                break
            past_reaction = reaction_day(report.report_date, report.report_time)
            past_day = past_reaction
            for _ in range(lead):
                past_day = previous_trading_day(past_day)
            spot = closes.get(past_day)
            rate = self._rate_or_none(rates, past_day)
            if spot is None or rate is None:
                continue
            iv = _archived_atm_iv(
                option_bars_on(session, ctx.ticker, past_day),
                Market(past_day, spot, rate),
                past_reaction,
            )
            if iv is not None:
                ivs.append(iv)
        return ivs

    def _rate(self, rates: Mapping[date, float], day: date) -> float:
        rate = self._rate_or_none(rates, day)
        if rate is None:
            raise DataError("fred", f"{RATE_SERIES}: no value within the last days before {day}")
        return rate

    def _rate_or_none(self, rates: Mapping[date, float], day: date) -> float | None:
        known = [
            d for d in rates if day - timedelta(days=self._settings.rate_max_age_days) <= d <= day
        ]
        return rates[max(known)] if known else None


def _rates(fred: FredSource, start: date, end: date) -> dict[date, float]:
    """DGS3MO в долях (3,9% → 0.039); пропуски FRED не значения."""
    return {
        o.date: o.value / 100
        for o in fred.observations(RATE_SERIES, start, end)
        if o.value is not None
    }


def _intraday_spot(source: OptionsSource, ticker: str, day: date, as_of: datetime) -> float:
    """Цена акции — закрытие последней минутной свечи дня не позже запуска."""
    bars = [
        b
        for b in source.aggregates(ticker, 1, "minute", day, day, adjusted=False)
        if b.start <= as_of
    ]
    if not bars or bars[-1].close <= 0:
        raise DataError(SOURCE, f"{ticker}: no minute bars on {day} before {as_of:%H:%M}")
    return bars[-1].close


def _chain_atm(
    options: Sequence[ChainOption], spot: float
) -> tuple[ChainOption, ChainOption] | None:
    """Колл и пут страйка, ближайшего к цене, у которого обе ноги торговались."""
    calls = {o.strike: o for o in options if o.kind == "call"}
    puts = {o.strike: o for o in options if o.kind == "put"}
    strikes = sorted(set(calls) & set(puts), key=lambda k: (abs(k - spot), k))
    return (calls[strikes[0]], puts[strikes[0]]) if strikes else None


def _chain_skew(options: Sequence[ChainOption], delta: float) -> float | None:
    """IV пута с дельтой ближе всего к −delta минус IV колла с дельтой ближе всего к +delta."""

    def nearest(kind: OptionType, target: float) -> ChainOption | None:
        found = [o for o in options if o.kind == kind and o.delta is not None]
        return min(found, key=lambda o: abs((o.delta or 0) - target), default=None)

    put, call = nearest("put", -delta), nearest("call", delta)
    return None if put is None or call is None else put.iv - call.iv


def _spot(closes: Mapping[date, float], ticker: str, day: date) -> float:
    spot = closes.get(day)
    if spot is None or not isfinite(spot) or spot <= 0:
        raise DataError(SOURCE, f"{ticker}: no stock close on {day}")
    return spot


def _iv(bar: OptionDailyBar, market: Market) -> float | None:
    return implied_volatility(
        bar.option_type,
        bar.close,
        market.spot,
        bar.strike,
        years_to_expiration(market.day, bar.expiration),
        market.rate,
    )


def _mean_iv(call: OptionDailyBar, put: OptionDailyBar, market: Market) -> float | None:
    values = [v for v in (_iv(call, market), _iv(put, market)) if v is not None]
    return statistics.fmean(values) if values else None


def _strike_for_delta(call_delta: float, sigma: float, years: float, market: Market) -> float:
    """Страйк, у колла которого дельта call_delta (у пута того же страйка — call_delta − 1)."""
    d1 = NormalDist().inv_cdf(call_delta)
    root = sqrt(years)
    return market.spot * exp(-d1 * sigma * root + (market.rate + sigma**2 / 2) * years)


def _archived_atm_iv(
    bars: Sequence[OptionDailyBar], market: Market, reaction: date
) -> float | None:
    """ATM IV из архива за день: ближайшая экспирация не раньше реакции, страйк ближе к цене."""
    eligible = [b for b in bars if b.expiration >= reaction and b.close > 0]
    if not eligible:
        return None
    expiration = min(b.expiration for b in eligible)
    calls = {
        b.strike: b for b in eligible if b.expiration == expiration and b.option_type == "call"
    }
    puts = {b.strike: b for b in eligible if b.expiration == expiration and b.option_type == "put"}
    strikes = sorted(set(calls) & set(puts), key=lambda k: (abs(k - market.spot), k))
    return _mean_iv(calls[strikes[0]], puts[strikes[0]], market) if strikes else None


def _trading_days_between(day: date, reaction: date) -> int:
    """Сколько торговых дней от day до реакции (day < reaction)."""
    count, current = 0, reaction
    while current > day:
        current = previous_trading_day(current)
        count += 1
    return count
