"""Данные выхода сделок бэктеста (T12): `make backtest-data ARGS="--all"` или `--ticker NFLX`.

Лимит Massive на опционные запросы (~5 в минуту, по наблюдению) — загрузка всей вселенной
занимает часы; прерванная загрузка продолжается с места остановки.
"""

import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from adapters.cache import RedisCache
from adapters.massive.client import MassiveClient, massive_api_key
from backtest.build_archive import parse_args
from backtest.exit_data import ExitDataLoader, ExitDataReport
from core.config import load_config
from core.db.session import create_db_engine, database_url
from core.session_guard import to_et

logger = logging.getLogger("backtest.load_exit_data")


def summary(report: ExitDataReport) -> str:
    """Одна строка итога по компании."""
    signals = ", ".join(f"{k} {v}" for k, v in sorted(report.signals.items()))
    ready = ", ".join(f"{k} {v}" for k, v in sorted(report.ready.items())) or "—"
    return (
        f"{report.ticker}: сигналы [{signals}] | данные готовы [{ready}] | "
        f"минутных рядов скачано {report.minute_series_saved} | без данных {len(report.failures)}"
    )


def main(argv: Sequence[str] | None = None, today: date | None = None) -> int:  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    config = load_config()
    tickers = parse_args(argv, config.universe.tickers())
    massive = config.sources.massive
    cache = RedisCache.from_env(config.sources.redis.timeout_seconds)
    key = massive_api_key()
    loader = ExitDataLoader(
        options=MassiveClient.create_history(massive, key, cache),
        stocks=MassiveClient.create(massive, key, cache),
        settings=massive.history,
        thresholds=config.thresholds,
        today=today or to_et(datetime.now(UTC)).date(),
    )
    with Session(create_db_engine(database_url())) as session:
        for ticker in tickers:
            report = loader.load(session, ticker)
            logger.info(summary(report))
            for report_date, reason in report.failures:
                logger.info("  %s: %s", report_date, reason)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
