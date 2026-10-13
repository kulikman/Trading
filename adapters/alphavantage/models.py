"""Модели ответов Alpha Vantage — по документации и записанным ответам (13.10.2026).

Числа приходят строками ("2.93"), «нет значения» — "None" или "" (BlankAsNoneModel).
"""

from datetime import date
from typing import Literal

from pydantic import Field

from adapters.api_model import BlankAsNoneModel
from core.domain.types import ReportTime

TIME_OF_DAY_TO_REPORT_TIME: dict[str, ReportTime] = {"pre-market": "BMO", "post-market": "AMC"}
CALENDAR_COLUMNS = (
    "symbol",
    "name",
    "reportDate",
    "fiscalDateEnding",
    "estimate",
    "currency",
    "timeOfTheDay",
)


def report_time_from_time_of_day(value: str | None) -> ReportTime | None:
    """pre-market → BMO, post-market → AMC; пусто (у ~77% строк календаря) — None."""
    if not value:
        return None
    return TIME_OF_DAY_TO_REPORT_TIME.get(value.strip().lower())


class AvCalendarRow(BlankAsNoneModel):
    """Строка CSV EARNINGS_CALENDAR."""

    symbol: str
    name: str | None = None
    report_date: date = Field(alias="reportDate")
    fiscal_date_ending: date | None = Field(default=None, alias="fiscalDateEnding")
    estimate: float | None = None
    currency: str | None = None
    time_of_the_day: str | None = Field(default=None, alias="timeOfTheDay")

    @property
    def report_time(self) -> ReportTime | None:
        return report_time_from_time_of_day(self.time_of_the_day)


class AvQuarterlyEarning(BlankAsNoneModel):
    """quarterlyEarnings[] из EARNINGS. Только EPS, без выручки."""

    fiscal_date_ending: date = Field(alias="fiscalDateEnding")
    reported_date: date | None = Field(default=None, alias="reportedDate")
    reported_eps: float | None = Field(default=None, alias="reportedEPS")
    estimated_eps: float | None = Field(default=None, alias="estimatedEPS")
    surprise: float | None = None
    surprise_percentage: float | None = Field(default=None, alias="surprisePercentage")
    report_time_raw: str | None = Field(default=None, alias="reportTime")

    @property
    def report_time(self) -> ReportTime | None:
        return report_time_from_time_of_day(self.report_time_raw)


class AvEarnings(BlankAsNoneModel):
    symbol: str
    quarterly: list[AvQuarterlyEarning] = Field(alias="quarterlyEarnings")


class AvEstimate(BlankAsNoneModel):
    """estimates[] из EARNINGS_ESTIMATES: консенсус, его разброс и пересмотры за 7–90 дней."""

    date: date
    horizon: Literal["fiscal quarter", "fiscal year"]
    eps_estimate_average: float | None = None
    eps_estimate_high: float | None = None
    eps_estimate_low: float | None = None
    eps_estimate_analyst_count: float | None = None
    eps_estimate_average_7_days_ago: float | None = None
    eps_estimate_average_30_days_ago: float | None = None
    eps_estimate_average_60_days_ago: float | None = None
    eps_estimate_average_90_days_ago: float | None = None
    eps_estimate_revision_up_trailing_7_days: float | None = None
    eps_estimate_revision_down_trailing_7_days: float | None = None
    eps_estimate_revision_up_trailing_30_days: float | None = None
    eps_estimate_revision_down_trailing_30_days: float | None = None
    revenue_estimate_average: float | None = None
    revenue_estimate_high: float | None = None
    revenue_estimate_low: float | None = None
    revenue_estimate_analyst_count: float | None = None
