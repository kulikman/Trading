"""Агент «Консенсус» (SPEC §8): пересмотры и разброс консенсуса EPS перед отчётом (T−10, T−3).

Источник — Alpha Vantage EARNINGS_ESTIMATES (бесплатно 25 запросов в день, один запрос на запуск).
Строка — фискальный квартал отчёта: последний конец квартала не позже даты отчёта и не раньше
max_quarter_lag_days до неё.

- revision_trend_7_90 — изменение консенсуса за 90 дней:
  (текущий − 90 дней назад) / |90 дней назад|;
  толкование имени признака — наше (SPEC не расписывает), записано в OPEN_QUESTIONS.md;
- revision_trend_7d — то же за 7 дней (последние пересмотры);
- estimate_dispersion — (максимум − минимум) / |среднее|;
- revisions_net_30d — пересмотров вверх минус вниз за 30 дней (доля от числа аналитиков).
Знаменатели не меньше min_abs_eps: при EPS около нуля доли теряют смысл.
"""

from collections.abc import Sequence
from datetime import timedelta
from typing import Protocol

from pydantic import BaseModel

from adapters.alphavantage.models import AvEstimate
from adapters.errors import DataError
from core.config.thresholds import ConsensusAgent
from core.registry.protocols import EventContext, Trigger

SOURCE = "alphavantage"
STAGES = ("T-10", "T-3")


class EstimatesSource(Protocol):
    def earnings_estimates(self, symbol: str) -> list[AvEstimate]:
        """Оценки аналитиков по кварталам и годам."""


class ConsensusFeatures(BaseModel):
    revision_trend_7_90: float | None = None
    revision_trend_7d: float | None = None
    estimate_dispersion: float | None = None
    revisions_net_30d: float | None = None
    analyst_count: float | None = None


class ConsensusAgentPlugin:
    id = "consensus"
    version = "0.1.0"
    triggers: Sequence[Trigger] = tuple(Trigger("stage", s) for s in STAGES)
    reads: Sequence[str] = ("alphavantage:EARNINGS_ESTIMATES",)
    output_schema = ConsensusFeatures

    def __init__(self, source: EstimatesSource, settings: ConsensusAgent) -> None:
        self._source = source
        self._settings = settings

    def run(self, ctx: EventContext) -> ConsensusFeatures:
        earliest = ctx.report_date - timedelta(days=self._settings.max_quarter_lag_days)
        quarters = [
            e
            for e in self._source.earnings_estimates(ctx.ticker)
            if e.horizon == "fiscal quarter" and earliest <= e.date <= ctx.report_date
        ]
        if not quarters:
            raise DataError(
                SOURCE, f"{ctx.ticker}: no quarter estimate for report {ctx.report_date}"
            )
        row = max(quarters, key=lambda e: e.date)
        average = row.eps_estimate_average
        count = row.eps_estimate_analyst_count
        up, down = (
            row.eps_estimate_revision_up_trailing_30_days,
            row.eps_estimate_revision_down_trailing_30_days,
        )
        return ConsensusFeatures(
            revision_trend_7_90=self._change(average, row.eps_estimate_average_90_days_ago),
            revision_trend_7d=self._change(average, row.eps_estimate_average_7_days_ago),
            estimate_dispersion=(
                None
                if average is None or row.eps_estimate_high is None or row.eps_estimate_low is None
                else (row.eps_estimate_high - row.eps_estimate_low) / self._base(average)
            ),
            # пропуск у Alpha Vantage — «нет пересмотров» (в ответе null вместо 0)
            revisions_net_30d=((up or 0.0) - (down or 0.0)) / count if count else None,
            analyst_count=count,
        )

    def _change(self, now: float | None, before: float | None) -> float | None:
        if now is None or before is None:
            return None
        return (now - before) / self._base(before)

    def _base(self, value: float) -> float:
        return max(abs(value), self._settings.min_abs_eps)
