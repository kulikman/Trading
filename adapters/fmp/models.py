"""Модели ответов Financial Modeling Prep — analyst-estimates endpoint.

FMP отдаёт текущий консенсус EPS (среднее/max/min, число аналитиков) без истории
пересмотров. Поля revision_trend_* и revisions_net_30d будут None при использовании
FMP как fallback; estimate_dispersion и analyst_count доступны.
"""

from datetime import date

from pydantic import Field

from adapters.alphavantage.models import AvEstimate
from adapters.api_model import ApiModel


class FmpEstimateRow(ApiModel):
    """Одна строка из /v3/analyst-estimates/{symbol}?period=quarter."""

    date: date
    estimated_eps_avg: float | None = Field(default=None, alias="estimatedEpsAvg")
    estimated_eps_high: float | None = Field(default=None, alias="estimatedEpsHigh")
    estimated_eps_low: float | None = Field(default=None, alias="estimatedEpsLow")
    number_analyst_eps: float | None = Field(default=None, alias="numberAnalystEstimatedEps")

    def to_av_estimate(self) -> AvEstimate:
        """Конвертирует в AvEstimate; revision-поля оставляет None."""
        return AvEstimate(
            date=self.date,
            horizon="fiscal quarter",
            eps_estimate_average=self.estimated_eps_avg,
            eps_estimate_high=self.estimated_eps_high,
            eps_estimate_low=self.estimated_eps_low,
            eps_estimate_analyst_count=self.number_analyst_eps,
        )
