"""Преобразование календаря Finnhub в доменные записи."""

import logging
from collections.abc import Collection, Iterable
from datetime import date

from adapters.finnhub.models import FinnhubEarning
from core.domain.earnings import ConsensusSnapshot

logger = logging.getLogger(__name__)


def consensus_snapshots(
    items: Iterable[FinnhubEarning], as_of: date, tickers: Collection[str]
) -> list[ConsensusSnapshot]:
    """Снимок консенсуса для компаний вселенной; без оценки или без квартала — пропуск с логом.

    Дубль (тикер, период) внутри ответа — побеждает последний: в одной вставке Postgres
    не может обновить строку дважды.
    """
    by_key: dict[tuple[str, str], ConsensusSnapshot] = {}
    for item in items:
        if item.symbol not in tickers:
            continue
        period = item.fiscal_period
        if period is None or (item.eps_estimate is None and item.revenue_estimate is None):
            logger.info("consensus skipped", extra={"ticker": item.symbol, "date": str(item.date)})
            continue
        by_key[(item.symbol, period)] = ConsensusSnapshot(
            ticker=item.symbol,
            fiscal_period=period,
            as_of=as_of,
            eps_estimate=item.eps_estimate,
            rev_estimate=item.revenue_estimate,
        )
    return list(by_key.values())
