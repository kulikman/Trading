"""Ответы Alpha Vantage → доменные модели."""

from adapters.alphavantage.models import AvEarnings
from core.domain.earnings import ReportedEarnings


def reported_earnings(history: AvEarnings) -> list[ReportedEarnings]:
    """Все прошлые отчёты с датой публикации, по возрастанию даты (у источника — с 1996 г.)."""
    rows = [
        ReportedEarnings(
            ticker=history.symbol,
            report_date=q.reported_date,
            report_time=q.report_time,
            fiscal_period_end=q.fiscal_date_ending,
            eps_consensus=q.estimated_eps,
            eps_actual=q.reported_eps,
            eps_surprise_pct=q.surprise_percentage,
        )
        for q in history.quarterly
        if q.reported_date is not None
    ]
    return sorted(rows, key=lambda r: r.report_date)
