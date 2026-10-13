"""Квартальные финансы из XBRL companyfacts (вкладка «Финансы», DASHBOARD.md §4.5).

Тонкости XBRL, найденные на живых данных:
- денежный поток и часть строк приходят нарастающим итогом с начала года — квартал = разница двух
  итогов с одним началом периода;
- 4-го квартала отдельно нет (только год из 10-K) — Q4 = год − 9 месяцев;
- у разных компаний разные теги (у GS выручка — RevenuesNetOfInterestExpense) — варианты из конфига;
- EPS неаддитивен — разницей не считается, Q4 EPS остаётся пустым.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from adapters.edgar.models import CompanyFacts, XbrlFact
from core.config.sources import EdgarFinancials
from core.domain.financials import FinancialQuarter

ONE_DAY = timedelta(days=1)


@dataclass(frozen=True)
class QuarterValue:
    period_start: date
    period_end: date
    value: float
    derived: bool
    concept: str
    unit: str
    form: str
    accession: str
    filed: date


def _days(start: date, end: date) -> int:
    return (end - start).days + 1


def _latest_by_period(facts: Iterable[XbrlFact]) -> dict[tuple[date, date], XbrlFact]:
    """Один факт на период: побеждает поданный позже (пересчёты прошлых периодов)."""
    latest: dict[tuple[date, date], XbrlFact] = {}
    for fact in facts:
        if fact.start is None:
            continue
        key = (fact.start, fact.end)
        if key not in latest or fact.filed > latest[key].filed:
            latest[key] = fact
    return latest


def quarterly_values(
    facts: Iterable[XbrlFact],
    *,
    concept: str,
    unit: str,
    additive: bool,
    min_days: int,
    max_days: int,
) -> dict[date, QuarterValue]:
    """Кварталы по дате окончания: прямые факты длиной в квартал, затем — разницы итогов."""
    by_period = _latest_by_period(facts)
    quarters: dict[date, QuarterValue] = {}
    for (start, end), fact in by_period.items():
        if min_days <= _days(start, end) <= max_days:
            quarters[end] = QuarterValue(
                start, end, fact.val, False, concept, unit, fact.form, fact.accn, fact.filed
            )
    if not additive:
        return quarters
    for (start, shorter_end), shorter in by_period.items():
        for (other_start, longer_end), longer in by_period.items():
            if other_start != start or longer_end <= shorter_end or longer_end in quarters:
                continue
            quarter_start = shorter_end + ONE_DAY
            if min_days <= _days(quarter_start, longer_end) <= max_days:
                quarters[longer_end] = QuarterValue(
                    quarter_start,
                    longer_end,
                    longer.val - shorter.val,
                    True,
                    concept,
                    unit,
                    longer.form,
                    longer.accn,
                    longer.filed,
                )
    return quarters


def merge_candidates(per_concept: Sequence[dict[date, QuarterValue]]) -> dict[date, QuarterValue]:
    """Тег раньше в списке побеждает; следующие заполняют пропуски (смена тега со временем)."""
    merged: dict[date, QuarterValue] = {}
    for values in per_concept:
        for end, value in values.items():
            merged.setdefault(end, value)
    return merged


def financial_quarters(
    ticker: str, facts: CompanyFacts, settings: EdgarFinancials
) -> list[FinancialQuarter]:
    """Последние settings.quarters кварталов по каждому показателю из settings.concepts."""
    rows: list[FinancialQuarter] = []
    for metric, candidates in settings.concepts.items():
        additive = metric not in settings.non_additive_metrics
        per_concept: list[dict[date, QuarterValue]] = []
        for concept in candidates:
            found = facts.concept(concept)
            if found is None:
                continue
            unit, concept_facts = found
            per_concept.append(
                quarterly_values(
                    concept_facts,
                    concept=concept,
                    unit=unit,
                    additive=additive,
                    min_days=settings.quarter_days_min,
                    max_days=settings.quarter_days_max,
                )
            )
        merged = merge_candidates(per_concept)
        for end in sorted(merged, reverse=True)[: settings.quarters]:
            q = merged[end]
            rows.append(
                FinancialQuarter(
                    ticker=ticker,
                    metric=metric,
                    period_start=q.period_start,
                    period_end=q.period_end,
                    value=q.value,
                    unit=q.unit,
                    derived=q.derived,
                    concept=q.concept,
                    form=q.form,
                    accession=q.accession,
                    filed=q.filed,
                )
            )
    return rows
