"""Модели ответов Finnhub — по схеме https://finnhub.io/static/swagger.json (13.10.2026)."""

import logging
from datetime import date

from pydantic import Field

from adapters.api_model import ApiModel
from core.domain.types import ReportTime

logger = logging.getLogger(__name__)

HOUR_TO_REPORT_TIME: dict[str, ReportTime] = {"bmo": "BMO", "amc": "AMC", "dmh": "DURING"}


def report_time_from_hour(hour: str | None) -> ReportTime | None:
    """bmo → BMO, amc → AMC, dmh → DURING; пусто или неизвестно — None (не угадываем)."""
    if not hour:
        return None
    mapped = HOUR_TO_REPORT_TIME.get(hour.strip().lower())
    if mapped is None:
        logger.warning("unknown finnhub hour value", extra={"hour": hour})
    return mapped


class FinnhubEarning(ApiModel):
    """Элемент /calendar/earnings (EarningRelease). EPS — non-GAAP."""

    symbol: str
    date: date
    hour: str | None = None
    year: int | None = None
    quarter: int | None = None
    eps_estimate: float | None = Field(default=None, alias="epsEstimate")
    eps_actual: float | None = Field(default=None, alias="epsActual")
    revenue_estimate: float | None = Field(default=None, alias="revenueEstimate")
    revenue_actual: float | None = Field(default=None, alias="revenueActual")

    @property
    def report_time(self) -> ReportTime | None:
        return report_time_from_hour(self.hour)

    @property
    def fiscal_period(self) -> str | None:
        """'2026Q3' или None, если год / квартал не пришли.

        TODO(OPEN_QUESTIONS): в схеме EarningRelease это «Earnings year/quarter» — фискальные или
        календарные, не уточнено; у EarningResult (/stock/earnings) — фискальные.
        """
        if self.year is None or self.quarter is None:
            return None
        return f"{self.year}Q{self.quarter}"


class FinnhubEpsResult(ApiModel):
    """Элемент /stock/earnings (EarningResult): факт против оценки по фискальным кварталам."""

    symbol: str
    period: date
    year: int | None = None
    quarter: int | None = None
    actual: float | None = None
    estimate: float | None = None
    surprise: float | None = None
    surprise_percent: float | None = Field(default=None, alias="surprisePercent")
