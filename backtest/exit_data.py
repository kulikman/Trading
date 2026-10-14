"""Данные выхода сделок бэктеста (T12): минутные цены ног в день реакции, контракты iron condor.

Для каждого отчёта с сигналом (см. backtest/signals.py):
- стрэддл — ATM-пара из архива T10; докачиваются минутные цены обеих ног до времени выхода;
- iron condor — справочник контрактов на день накануне, страйки ±1 / ±2 implied move,
  дневные цены 4 ног (вход по закрытию накануне) и их минутные цены в день реакции.
Всё сохраняется в архив; повторный запуск качает только недостающее. Commit — после отчёта.
"""

import logging
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Literal, Protocol

from sqlalchemy.orm import Session

from adapters.errors import DataError
from adapters.massive.history import (
    option_bars,
    spot_on,
    stock_closes,
    straddle_from_bars,
)
from adapters.massive.models import Bar, ContractType, OptionContract
from backtest.option_history import STOCK_PADDING_DAYS, StockBarsSource
from backtest.signals import CondorStrikes, Construction, Signal, condor_strikes, signals
from core.config.sources import MassiveHistory
from core.config.thresholds import Thresholds
from core.db.store import (
    earnings_history,
    option_bars_on,
    option_minute_bars,
    save_option_bars,
    save_option_minute_bars,
)
from core.domain.options import OptionMinuteBar
from core.session_guard import ET, session, to_et

logger = logging.getLogger(__name__)

STRIKE_SEARCH_MARGIN = 0.5  # справочник — страйки до (wing + 0.5) implied move от цены


class OptionDataSource(Protocol):
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
        timespan: Literal["day", "minute"],
        start: date,
        end: date,
        *,
        adjusted: bool = True,
    ) -> list[Bar]:
        """Свечи."""


@dataclass(frozen=True)
class CondorLegs:
    strikes: CondorStrikes
    long_put: str
    short_put: str
    short_call: str
    long_call: str

    @property
    def tickers(self) -> list[str]:
        return [self.long_put, self.short_put, self.short_call, self.long_call]


@dataclass
class ExitDataReport:
    ticker: str
    signals: Counter[str] = field(default_factory=Counter)
    ready: Counter[str] = field(default_factory=Counter)
    failures: list[tuple[date, str]] = field(default_factory=list)
    minute_series_saved: int = 0


class ExitDataLoader:
    def __init__(
        self,
        *,
        options: OptionDataSource,
        stocks: StockBarsSource,
        settings: MassiveHistory,
        thresholds: Thresholds,
        today: date,
    ) -> None:
        self._options = options
        self._stocks = stocks
        self._settings = settings
        self._thresholds = thresholds
        self._today = today

    @property
    def since(self) -> date:
        return self._today - timedelta(days=self._settings.archive_days)

    def signals(self, session: Session, ticker: str) -> list[Signal]:
        """Сигналы по отчётам компании в окне опционов."""
        return signals(
            ticker,
            earnings_history(session, ticker, date.min),
            since=self.since,
            today=self._today,
            settings=self._thresholds.backtest,
            constructions=self._thresholds.constructions,
        )

    def load(self, db: Session, ticker: str) -> ExitDataReport:
        """Докачать данные выхода для всех сигналов компании."""
        report = ExitDataReport(ticker)
        found = self.signals(db, ticker)
        for item in found:
            report.signals[item.construction or item.reason or "none"] += 1
        active = [(s, s.construction) for s in found if s.construction is not None]
        if not active:
            return report
        bars = self._stocks.aggregates(
            ticker,
            1,
            "day",
            active[0][0].days.pre - timedelta(days=STOCK_PADDING_DAYS),
            active[-1][0].days.reaction,
            adjusted=False,
        )
        closes = stock_closes(bars)
        for item, construction in active:
            try:
                spot = spot_on(closes, ticker, item.days)
                legs = self._legs(db, ticker, item, construction, spot)
                report.minute_series_saved += self._ensure_minutes(db, legs, item.days.reaction)
            except DataError as exc:
                report.failures.append((item.days.report_date, f"{construction}: {exc.detail}"))
                logger.warning(
                    "no exit data",
                    extra={"ticker": ticker, "report_date": item.days.report_date.isoformat()},
                )
            else:
                report.ready[construction] += 1
            db.commit()
        return report

    def _legs(
        self, db: Session, ticker: str, item: Signal, construction: Construction, spot: float
    ) -> list[str]:
        archived = option_bars_on(db, ticker, item.days.pre)
        straddle = straddle_from_bars(
            ticker, item.days, spot, archived, self._settings.risk_free_rate
        )
        if construction == "straddle":
            return [straddle.call_ticker, straddle.put_ticker]
        legs, contracts = self._condor(ticker, item, spot, straddle.expiration)
        have = {b.option_ticker for b in archived}
        start = item.days.pre - timedelta(days=self._settings.days_before)
        end = item.days.reaction + timedelta(days=self._settings.days_after)
        for leg in legs.tickers:
            if leg not in have:
                daily = self._options.aggregates(leg, 1, "day", start, end)
                save_option_bars(db, option_bars(contracts[leg], daily))
        return legs.tickers

    def _condor(
        self, ticker: str, item: Signal, spot: float, expiration: date
    ) -> tuple[CondorLegs, dict[str, OptionContract]]:
        condor = self._thresholds.constructions.iron_condor
        reach = (condor.wing_implied_moves + STRIKE_SEARCH_MARGIN) * item.implied_move
        contracts = self._options.option_contracts(
            ticker,
            expiration_gte=expiration,
            expiration_lte=expiration,
            as_of=item.days.pre,
            strike_gte=spot * (1 - reach),
            strike_lte=spot * (1 + reach),
        )
        calls = {c.strike_price: c for c in contracts if c.contract_type == "call"}
        puts = {c.strike_price: c for c in contracts if c.contract_type == "put"}
        strikes = condor_strikes(
            sorted(calls),
            sorted(puts),
            spot,
            item.implied_move,
            condor.short_implied_moves,
            condor.wing_implied_moves,
        )
        if strikes is None:
            raise DataError("massive", f"{ticker} {item.days.report_date}: no condor strikes")
        legs = CondorLegs(
            strikes,
            puts[strikes.long_put].ticker,
            puts[strikes.short_put].ticker,
            calls[strikes.short_call].ticker,
            calls[strikes.long_call].ticker,
        )
        return legs, {c.ticker: c for c in contracts}

    def _ensure_minutes(self, db: Session, legs: Sequence[str], day: date) -> int:
        """Минутные цены ног с открытия до времени выхода; уже сохранённые не качаются."""
        start, end = exit_window(day, self._thresholds.backtest.exit_time_et)
        stored = option_minute_bars(db, legs, start, end)
        saved = 0
        for leg in legs:
            if stored.get(leg):
                continue
            bars = self._options.aggregates(leg, 1, "minute", day, day)
            rows = [
                OptionMinuteBar(
                    option_ticker=leg,
                    minute=bar.start,
                    open=bar.open,
                    high=bar.high,
                    low=bar.low,
                    close=bar.close,
                    volume=bar.volume,
                    vwap=bar.vwap,
                    transactions=bar.transactions,
                )
                for bar in bars
                if start <= to_et(bar.start) < end
            ]
            save_option_minute_bars(db, rows)
            saved += bool(rows)
        return saved


def exit_window(day: date, exit_time: time) -> tuple[datetime, datetime]:
    """С открытия основной сессии до времени выхода включительно (минута выхода — в окне)."""
    trading = session(day)
    if trading is None:
        raise DataError("massive", f"{day} is not a trading day")
    return trading.open, datetime.combine(day, exit_time, tzinfo=ET) + timedelta(minutes=1)
