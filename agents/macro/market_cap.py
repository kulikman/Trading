"""Обновление company.market_cap_usd_m из Finnhub /stock/profile2.

Запуск вручную: make populate-market-cap
Автоматически: задача market-cap-daily в APScheduler (07:30 ET, пн-пт).
"""

import logging
import time

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.errors import DataError
from adapters.finnhub.client import FinnhubClient, finnhub_api_key
from core.config import load_config
from core.db import models as orm
from core.db.session import create_db_engine
from core.error_log import logged_job
from core.scheduler.jobs import engine

logger = logging.getLogger(__name__)


def populate_market_caps(pause_seconds: float = 0.5) -> dict[str, float | None]:
    """Обходит все компании, запрашивает профиль Finnhub, сохраняет капитализацию."""
    config = load_config()
    finnhub = FinnhubClient.create(config.sources.finnhub, finnhub_api_key())
    engine = create_db_engine()
    results: dict[str, float | None] = {}

    with Session(engine) as session:
        tickers: list[str] = list(
            session.scalars(select(orm.Company.ticker).order_by(orm.Company.ticker))
        )
        logger.info("компаний для обновления: %d", len(tickers))

        for ticker in tickers:
            try:
                profile = finnhub.company_profile(ticker)
                cap = profile.market_capitalization
                company = session.get(orm.Company, ticker)
                if company is not None:
                    company.market_cap_usd_m = cap
                results[ticker] = cap
                logger.info("  %s: %.0f M", ticker, cap or 0)
            except DataError as exc:
                logger.warning("  %s: ошибка — %s", ticker, exc)
                results[ticker] = None
            time.sleep(pause_seconds)

        session.commit()

    logger.info("готово")
    return results


@logged_job("market-cap-daily", lambda: engine())
def run_market_cap_refresh() -> None:
    """Точка входа для APScheduler: обновляет капитализацию всех компаний из Finnhub."""
    populate_market_caps()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    populate_market_caps()
