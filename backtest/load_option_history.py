"""Архив опционов по прошлым отчётам (T10).

Запуск: `make load-options ARGS="--ticker NFLX"` или `ARGS="--all"`.

Лимиты: Massive (опционы) — ~5 запросов в минуту, Alpha Vantage — 25 в день. При исчерпании
лимита Alpha Vantage загрузка останавливается; повторный запуск продолжит с того же места.
"""

import argparse
import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from adapters.alphavantage.client import AlphaVantageClient, alphavantage_api_key
from adapters.cache import RedisCache
from adapters.massive.client import MassiveClient, massive_api_key
from backtest.option_history import EarningsSourceExhausted, OptionHistoryLoader, TickerReport
from core.config import load_config
from core.db.session import create_db_engine, database_url
from core.db.store import sync_universe
from core.session_guard import to_et

logger = logging.getLogger("backtest.load_option_history")


def parse_args(argv: Sequence[str] | None, universe: Sequence[str]) -> list[str]:
    """Тикеры для загрузки: --ticker (можно несколько) или --all (вся вселенная)."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", action="append", help="тикер из вселенной; можно повторять")
    group.add_argument("--all", action="store_true", help="вся вселенная")
    args = parser.parse_args(argv)
    tickers = list(universe) if args.all else [t.upper() for t in args.ticker]
    unknown = sorted(set(tickers) - set(universe))
    if unknown:
        parser.error(f"not in universe: {', '.join(unknown)}")
    return tickers


def summary(report: TickerReport) -> str:
    """Одна строка итога по компании."""
    moves = ", ".join(f"{s.days.report_date:%Y-%m-%d} {s.move:.1%}" for s in report.straddles)
    return (
        f"{report.ticker}: отчётов {report.events}, с implied move {len(report.straddles)}, "
        f"из архива {report.from_archive}, цен сохранено {report.bars_saved}, "
        f"без данных {len(report.failures)} | {moves}"
    )


def main(argv: Sequence[str] | None = None, today: date | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    config = load_config()
    tickers = parse_args(argv, config.universe.tickers())
    sources = config.sources
    cache = RedisCache.from_env(sources.redis.timeout_seconds)
    key = massive_api_key()
    loader = OptionHistoryLoader(
        options=MassiveClient.create_history(sources.massive, key, cache),
        stocks=MassiveClient.create(sources.massive, key, cache),
        earnings=AlphaVantageClient.create(sources.alphavantage, alphavantage_api_key(), cache),
        settings=sources.massive.history,
        today=today or to_et(datetime.now(UTC)).date(),
    )
    engine = create_db_engine(database_url())
    with Session(engine) as session:
        sync_universe(session, config.universe)
        session.commit()
        for ticker in tickers:
            try:
                report = loader.load(session, ticker)
            except EarningsSourceExhausted as exc:
                logger.warning("Остановлено: даты отчётов недоступны (%s). Продолжить завтра.", exc)
                return 1
            logger.info(summary(report))
            for report_date, reason in report.failures:
                logger.info("  %s: %s", report_date, reason)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
