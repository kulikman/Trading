"""Загрузка архива опционов вокруг прошлых отчётов и расчёт implied move (T10).

Для каждой компании:
1. даты прошлых отчётов — из earnings_track, а если их там нет (или нет EPS) — из Alpha Vantage
   EARNINGS (25 запросов в день): вся история с EPS записывается в earnings_track одним запросом;
2. закрытия акции — Massive, без поправки на сплиты (опционы до сплита — в тогдашних страйках);
3. по каждому отчёту: если пара ATM уже в архиве — расчёт без запросов, иначе скачивание цен
   контрактов (с лимитом частоты) в option_daily_bar;
4. implied move — в earnings_track.

После каждого отчёта — commit: прерванная загрузка продолжается с того же места.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Literal, Protocol

from sqlalchemy.orm import Session

from adapters.alphavantage.mapping import reported_earnings
from adapters.alphavantage.models import AvEarnings
from adapters.errors import DataError
from adapters.massive.history import (
    EventDays,
    HistoricalStraddle,
    OptionHistorySource,
    fetch_event_bars,
    spot_on,
    stock_closes,
    straddle_from_bars,
)
from adapters.massive.models import Bar
from core.config.sources import MassiveHistory
from core.db.store import (
    earnings_dates,
    has_reported_eps,
    option_bars_on,
    save_option_bars,
    save_reported_earnings,
    set_implied_move,
)
from core.domain.types import ReportTime

logger = logging.getLogger(__name__)

STOCK_PADDING_DAYS = 10  # запас до начала окна: «накануне» первого отчёта может быть раньше него
STALE_DATES_DAYS = 120  # последний известный отчёт старше квартала с запасом — даты обновить


class EarningsHistorySource(Protocol):
    def earnings(self, symbol: str) -> AvEarnings:
        """История отчётов компании."""


class StockBarsSource(Protocol):
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
        """Свечи акции."""


class EarningsSourceExhausted(Exception):
    """Источник дат отчётов недоступен (лимит Alpha Vantage на день) — продолжить позже."""


@dataclass
class TickerReport:
    ticker: str
    straddles: list[HistoricalStraddle] = field(default_factory=list)
    failures: list[tuple[date, str]] = field(default_factory=list)
    from_archive: int = 0
    bars_saved: int = 0

    @property
    def events(self) -> int:
        return len(self.straddles) + len(self.failures)


class OptionHistoryLoader:
    def __init__(
        self,
        *,
        options: OptionHistorySource,
        stocks: StockBarsSource,
        earnings: EarningsHistorySource,
        settings: MassiveHistory,
        today: date,
        commit: Callable[[Session], None] = Session.commit,
    ) -> None:
        self._options = options
        self._stocks = stocks
        self._earnings = earnings
        self._settings = settings
        self._today = today
        self._commit = commit

    @property
    def since(self) -> date:
        """Первый день, за который у источника есть цены опционов."""
        return self._today - timedelta(days=self._settings.archive_days)

    def load(self, session: Session, ticker: str) -> TickerReport:
        """Архив и implied move по прошлым отчётам компании в окне доступа."""
        report = TickerReport(ticker)
        events = [
            days
            for days in (EventDays.of(d, t) for d, t in self._report_dates(session, ticker))
            if days.pre >= self.since and days.reaction < self._today
        ]
        if not events:
            return report
        closes = stock_closes(
            self._stocks.aggregates(
                ticker,
                1,
                "day",
                events[0].pre - timedelta(days=STOCK_PADDING_DAYS),
                events[-1].reaction,
                adjusted=False,
            )
        )
        for days in events:
            try:
                straddle = self._event(session, ticker, days, closes, report)
            except DataError as exc:
                logger.warning(
                    "no implied move for report",
                    extra={"ticker": ticker, "report_date": days.report_date.isoformat()},
                )
                report.failures.append((days.report_date, exc.detail))
            else:
                set_implied_move(session, ticker, days.report_date, straddle.move)
                report.straddles.append(straddle)
            self._commit(session)
        return report

    def _report_dates(self, session: Session, ticker: str) -> list[tuple[date, ReportTime | None]]:
        stored = earnings_dates(session, ticker, self.since)
        is_fresh = bool(stored) and stored[-1][0] >= self._today - timedelta(days=STALE_DATES_DAYS)
        if is_fresh and has_reported_eps(session, ticker):
            return stored
        try:
            history = self._earnings.earnings(ticker)
        except DataError as exc:
            raise EarningsSourceExhausted(f"{ticker}: {exc.detail}") from exc
        reports = reported_earnings(history)  # вся история EPS (с 1996 г.) — для модели p_beat
        save_reported_earnings(session, reports)
        self._commit(session)
        return [(r.report_date, r.report_time) for r in reports if r.report_date >= self.since]

    def _event(
        self,
        session: Session,
        ticker: str,
        days: EventDays,
        closes: dict[date, float],
        report: TickerReport,
    ) -> HistoricalStraddle:
        spot = spot_on(closes, ticker, days)
        rate = self._settings.risk_free_rate
        archived = option_bars_on(session, ticker, days.pre)
        if archived:
            # Цены этого отчёта уже скачивались (commit — только после полного отчёта): считаем по
            # архиву. Если подходящей пары не было тогда, повторное скачивание её не даст.
            report.from_archive += 1
            return straddle_from_bars(ticker, days, spot, archived, rate)
        bars = fetch_event_bars(self._options, ticker, days, spot, self._settings)
        report.bars_saved += save_option_bars(session, bars)
        return straddle_from_bars(ticker, days, spot, bars, rate)
