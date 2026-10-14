"""Сборка архива прошлых отчётов в earnings_track (T11) и отчёт о покрытии.

Запуск: `make build-archive ARGS="--ticker NFLX"` или `ARGS="--all"`.

По каждой компании:
1. даты, EPS и implied move — загрузчик T10 (Alpha Vantage EARNINGS + опционы Massive);
2. фактическое движение и move_ratio — закрытия акции Massive;
3. выручка-факт — квартальная выручка SEC XBRL (financial_quarter);
4. сверка даты отчёта с подачей 8-K о результатах (SEC).
Лимит Alpha Vantage исчерпан — шаг 1 пропускается для компаний без дат, остальные шаги идут
по тому, что уже есть в базе. Отчёт: reports/archive_coverage_<дата>.md.
"""

import argparse
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Protocol

from sqlalchemy.orm import Session

from adapters.alphavantage.client import AlphaVantageClient, alphavantage_api_key
from adapters.cache import RedisCache
from adapters.edgar.client import EdgarClient, sec_user_agent
from adapters.edgar.financials import financial_quarters
from adapters.edgar.models import CompanyFacts, Filing
from adapters.errors import DataError
from adapters.massive.client import MassiveClient, massive_api_key
from adapters.massive.history import EventDays, stock_closes
from backtest.archive_steps import (
    ArchiveStats,
    DateCheck,
    apply_moves,
    apply_revenue,
    check_dates,
    save_date_checks,
)
from backtest.coverage import coverage, render
from backtest.option_history import (
    STOCK_PADDING_DAYS,
    EarningsSourceExhausted,
    OptionHistoryLoader,
    StockBarsSource,
)
from core.config import load_config
from core.config.sources import EdgarSettings
from core.db.session import create_db_engine, database_url
from core.db.store import earnings_history, save_financial_quarters, sync_universe
from core.domain.earnings import EarningsTrack
from core.domain.financials import FinancialQuarter
from core.session_guard import to_et

logger = logging.getLogger("backtest.build_archive")

REPORTS_DIR = Path(__file__).resolve().parents[1] / "reports"


class SecSource(Protocol):
    def ticker_ciks(self) -> dict[str, int]:
        """Тикер → CIK."""

    def company_facts(self, cik: int) -> CompanyFacts:
        """XBRL-факты компании."""

    def earnings_releases(self, cik: int, since: date | None = None) -> list[Filing]:
        """8-K с пунктом 2.02."""


@dataclass
class TickerArchive:
    ticker: str
    stats: ArchiveStats = field(default_factory=ArchiveStats)
    checks: list[DateCheck] = field(default_factory=list)
    reports: int = 0
    dates_pending: bool = False  # нет дат: лимит Alpha Vantage — догрузится в следующий запуск


class ArchiveBuilder:
    def __init__(
        self,
        *,
        loader: OptionHistoryLoader,
        stocks: StockBarsSource,
        sec: SecSource,
        edgar: EdgarSettings,
        today: date,
        predecessor_ciks: Mapping[str, Sequence[int]] | None = None,
    ) -> None:
        self._loader = loader
        self._stocks = stocks
        self._sec = sec
        self._edgar = edgar
        self._today = today
        self._ciks: dict[str, int] | None = None
        self._predecessors = dict(predecessor_ciks or {})

    def build(self, session: Session, ticker: str) -> TickerArchive:
        """Все шаги по компании; commit — после каждого шага (прерывание не теряет сделанное)."""
        result = TickerArchive(ticker)
        try:
            self._loader.load(session, ticker)
        except EarningsSourceExhausted as exc:
            logger.warning("dates unavailable, other steps use stored data: %s", exc)
            result.dates_pending = True
        # Движения и сверка дат — за всю глубину цен акций (5 лет): прошлые движения нужны
        # сигналу бэктеста (T12); implied move и опционы — только в окне 2 лет.
        stock_since = self._today - timedelta(days=self._loader.settings.stock_history_days)
        rows = [
            r
            for r in earnings_history(session, ticker, stock_since)
            if r.report_date < self._today
            and EventDays.of(r.report_date, r.report_time).pre >= stock_since
        ]
        result.reports = sum(r.report_date >= self._loader.since for r in rows)
        if not rows:
            return result
        first = EventDays.of(rows[0].report_date, rows[0].report_time)
        last = EventDays.of(rows[-1].report_date, rows[-1].report_time)
        bars = self._stocks.aggregates(
            ticker,
            1,
            "day",
            max(first.pre - timedelta(days=STOCK_PADDING_DAYS), stock_since),
            last.reaction,
            adjusted=False,
        )
        apply_moves(session, ticker, rows, stock_closes(bars), self._today, result.stats)
        session.commit()
        try:
            self._sec_steps(session, ticker, rows, result)
        except DataError as exc:
            logger.warning("SEC data unavailable for %s: %s", ticker, exc.detail)
        session.commit()
        return result

    def _sec_steps(
        self, session: Session, ticker: str, rows: list[EarningsTrack], result: TickerArchive
    ) -> None:
        if self._ciks is None:
            self._ciks = self._sec.ticker_ciks()
        cik = self._ciks.get(ticker)
        if cik is None:
            raise DataError("edgar", f"{ticker}: no CIK")
        archive = self._edgar.archive
        settings = self._edgar.financials.model_copy(update={"quarters": archive.revenue_quarters})
        # Текущий регистрант первым: его значение за квартал важнее значения прежнего.
        ciks = [cik, *self._predecessors.get(ticker, [])]
        by_key: dict[tuple[str, date], FinancialQuarter] = {}
        for each in reversed(ciks):
            for quarter in financial_quarters(ticker, self._sec.company_facts(each), settings):
                by_key[(quarter.metric, quarter.period_end)] = quarter
        quarters = list(by_key.values())
        save_financial_quarters(session, quarters)
        result.stats.revenue_matched = apply_revenue(
            session, ticker, rows, quarters, archive.fiscal_end_tolerance_days
        )
        since = rows[0].report_date - timedelta(days=archive.filing_search_days)
        filings = [f for each in ciks for f in self._sec.earnings_releases(each, since=since)]
        result.checks = check_dates(ticker, rows, filings, archive.filing_search_days)
        save_date_checks(session, result.checks)


def parse_args(argv: Sequence[str] | None, universe: Sequence[str]) -> list[str]:
    """Тикеры: --ticker (можно несколько) или --all (вся вселенная)."""
    parser = argparse.ArgumentParser(description="Сборка архива прошлых отчётов (T11)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", action="append", help="тикер из вселенной; можно повторять")
    group.add_argument("--all", action="store_true", help="вся вселенная")
    args = parser.parse_args(argv)
    tickers = list(universe) if args.all else [t.upper() for t in args.ticker]
    unknown = sorted(set(tickers) - set(universe))
    if unknown:
        parser.error(f"not in universe: {', '.join(unknown)}")
    return tickers


def summary(result: TickerArchive) -> str:
    """Одна строка итога по компании."""
    stats = result.stats
    pending = (
        " | даты отчётов — в следующий запуск (лимит Alpha Vantage)" if result.dates_pending else ""
    )
    problems = sum(c.status != "ok" for c in result.checks)
    return (
        f"{result.ticker}: отчётов {result.reports}, движение {stats.moves}, "
        f"move_ratio {stats.ratios}, выручка {stats.revenue_matched}, "
        f"без цен {stats.missing_prices}, расхождений дат с 8-K {problems}{pending}"
    )


def main(argv: Sequence[str] | None = None, today: date | None = None) -> int:  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    config = load_config()
    tickers = parse_args(argv, config.universe.tickers())
    sources = config.sources
    day = today or to_et(datetime.now(UTC)).date()
    cache = RedisCache.from_env(sources.redis.timeout_seconds)
    key = massive_api_key()
    stocks = MassiveClient.create(sources.massive, key, cache)
    loader = OptionHistoryLoader(
        options=MassiveClient.create_history(sources.massive, key, cache),
        stocks=stocks,
        earnings=AlphaVantageClient.create(sources.alphavantage, alphavantage_api_key(), cache),
        settings=sources.massive.history,
        today=day,
    )
    builder = ArchiveBuilder(
        loader=loader,
        stocks=stocks,
        sec=EdgarClient.create(sources.edgar, sec_user_agent(), cache),
        edgar=sources.edgar,
        today=day,
        predecessor_ciks=config.universe.sec_predecessor_ciks(),
    )
    checks: list[DateCheck] = []
    pending: list[str] = []
    with Session(create_db_engine(database_url())) as session:
        sync_universe(session, config.universe)
        session.commit()
        for ticker in tickers:
            result = builder.build(session, ticker)
            logger.info(summary(result))
            checks += result.checks
            if result.dates_pending and not result.reports:
                pending.append(ticker)
        text = render(
            coverage(session, loader.since, day),
            checks,
            since=loader.since,
            until=day,
            pending=pending,
        )
    REPORTS_DIR.mkdir(exist_ok=True)
    path = REPORTS_DIR / f"archive_coverage_{day:%Y-%m-%d}.md"
    path.write_text(text, encoding="utf-8")
    logger.info("Отчёт о покрытии: %s", path)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
