"""Агент «Опционы» (SPEC §8): implied_move, skew_25d, term_slope, iv_rank.

Снимка цепочки с IV на тарифе нет (HTTP 403, проверено 14.10.2026), поэтому всё считается по
дневным ценам контрактов на закрытии торгового дня перед запуском — так же, как архив и бэктест
(T10, T12). IV — Блэк–Шоулз из цены закрытия, ставка — FRED DGS3MO на тот же день.

- implied_move — ATM-стрэддл ближайшей экспирации не раньше дня реакции / цена акции;
- atm_iv — средняя IV колла и пута этого страйка;
- skew_25d — IV пута 25Δ − IV колла 25Δ той же экспирации (> 0 — путы дороже, рынок боится падения);
- term_slope — ATM IV ближней − ATM IV дальней (≥ ближней + term_back_min_days): премия за отчёт;
- iv_rank — доля прошлых отчётов компании, у которых ATM IV за столько же торговых дней до реакции
  была ниже текущей (решение заказчика 14.10.2026: сравнение с той же стадией прошлых отчётов,
  а не со всеми днями года); прошлые цены — из архива option_daily_bar.

Скачанные цены контрактов сохраняются в архив — история для будущих iv_rank и бэктеста.
"""

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from math import exp, isfinite, sqrt
from statistics import NormalDist
from typing import Protocol

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
from adapters.massive.models import OptionContract
from adapters.massive.symbols import StockHistorySource, daily_bars
from core.config.sources import MassiveHistory
from core.config.thresholds import OptionsAgent
from core.db.store import earnings_history, option_bars_on, save_option_bars
from core.domain.options import OptionDailyBar
from core.domain.types import OptionType
from core.pricing.black_scholes import implied_volatility
from core.registry.protocols import EventContext, Trigger
from core.session_guard import previous_trading_day, reaction_day, to_et

SOURCE = "massive"
RATE_SERIES = "DGS3MO"
STAGES = ("T-7", "T-3", "T-1")
BAR_LOOKBACK_DAYS = 7  # цены контракта за неделю до дня оценки — один запрос


class OptionsSource(OptionHistorySource, StockHistorySource, Protocol):
    """Справочник контрактов, свечи контрактов и акции, история тикера."""


class OptionsFeatures(BaseModel):
    implied_move: float | None = None
    atm_iv: float | None = None
    skew_25d: float | None = None
    term_slope: float | None = None
    iv_rank: float | None = None
    iv_rank_reports: int = 0


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
        day = previous_trading_day(to_et(ctx.as_of).date())
        reaction = reaction_day(ctx.report_date, ctx.report_time)
        if day >= reaction:
            raise DataError(SOURCE, f"{ctx.ticker}: close {day} is not before reaction {reaction}")
        start = day - timedelta(days=self._settings.history_days)
        closes = stock_closes(daily_bars(self._source, ctx.ticker, start, day))
        rates = _rates(self._fred, start, day)
        market = Market(day, _spot(closes, ctx.ticker, day), self._rate(rates, day))
        fetched: list[OptionDailyBar] = []
        try:
            features = self._live(ctx.ticker, reaction, market, fetched)
        finally:
            save_option_bars(ctx.session, fetched)
        past = self._past_ivs(ctx.session, ctx, market.day, reaction, closes, rates)
        current = features.atm_iv
        if current is not None and len(past) >= self._settings.iv_rank_min_reports:
            features.iv_rank = sum(v < current for v in past) / len(past)
        features.iv_rank_reports = len(past)
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
