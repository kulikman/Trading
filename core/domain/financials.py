"""Квартальный финансовый показатель компании (DASHBOARD.md §4.5, источник — SEC XBRL)."""

from datetime import date

from core.domain.base import DomainModel


class FinancialQuarter(DomainModel):
    ticker: str
    metric: str  # ключ из config/sources.yaml edgar.financials.concepts
    period_start: date
    period_end: date
    value: float
    unit: str  # USD или USD/shares
    derived: bool  # True — посчитано разницей нарастающих итогов (например, Q4 = год − 9 месяцев)
    concept: str  # тег us-gaap, из которого взято значение
    form: str
    accession: str
    filed: date
