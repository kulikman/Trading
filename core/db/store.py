"""Запись данных источников в БД. Повторный запуск задачи не создаёт дублей (SPEC §13)."""

from collections.abc import Iterable
from datetime import date, datetime

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from core.config.universe import Universe
from core.db import models as orm
from core.domain.earnings import (
    ConsensusSnapshot,
    EarningsTrack,
    FeatureSnapshot,
    ReportedEarnings,
)
from core.domain.financials import FinancialQuarter
from core.domain.market import SectorSummary
from core.domain.news import NewsItem
from core.domain.options import OptionDailyBar, OptionMinuteBar
from core.domain.schedule import EventJob
from core.domain.types import DateCheckStatus, ReportTime


def save_consensus_snapshots(session: Session, snapshots: Iterable[ConsensusSnapshot]) -> int:
    """Снимок консенсуса на дату. Повтор за ту же дату обновляет значения, а не дублирует строку."""
    rows = [s.model_dump() for s in snapshots]
    if not rows:
        return 0
    statement = insert(orm.ConsensusSnapshot).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["ticker", "fiscal_period", "as_of"],
        set_={
            "eps_estimate": statement.excluded.eps_estimate,
            "rev_estimate": statement.excluded.rev_estimate,
            "updated_at": func.now(),
        },
    )
    session.execute(statement)
    return len(rows)


def save_news(session: Session, items: Iterable[NewsItem]) -> int:
    """Новости: статья уже есть — не трогаем (разметка T14 не затирается). Вернёт число новых."""
    rows = [i.model_dump() for i in items]
    if not rows:
        return 0
    statement = (
        insert(orm.NewsArticle)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["id"])
        .returning(orm.NewsArticle.id)
    )
    return len(session.execute(statement).scalars().all())


def save_financial_quarters(session: Session, quarters: Iterable[FinancialQuarter]) -> int:
    """Кварталы компании. Пересчёт (новая подача) обновляет значение и источник."""
    rows = [q.model_dump() for q in quarters]
    if not rows:
        return 0
    statement = insert(orm.FinancialQuarter).values(rows)
    updated = ("period_start", "value", "unit", "derived", "concept", "form", "accession", "filed")
    statement = statement.on_conflict_do_update(
        index_elements=["ticker", "metric", "period_end"],
        set_={**{c: statement.excluded[c] for c in updated}, "updated_at": func.now()},
    )
    session.execute(statement)
    return len(rows)


def save_option_bars(session: Session, bars: Iterable[OptionDailyBar]) -> int:
    """Дневные цены контрактов. Повторная загрузка обновляет цену (источник мог её уточнить)."""
    rows = [b.model_dump() for b in bars]
    if not rows:
        return 0
    statement = insert(orm.OptionDailyBar).values(rows)
    updated = ("open", "high", "low", "close", "volume", "vwap", "transactions")
    statement = statement.on_conflict_do_update(
        index_elements=["option_ticker", "day"],
        set_={**{c: statement.excluded[c] for c in updated}, "updated_at": func.now()},
    )
    session.execute(statement)
    return len(rows)


def save_reported_earnings(session: Session, reports: Iterable[ReportedEarnings]) -> int:
    """Прошлые отчёты в earnings_track: дата, время, фискальный квартал, EPS.

    Ключ — (ticker, report_date). Известное время отчёта пустым не затирается; EPS источника
    перезаписывается (он мог уточнить факт). Дубли даты в ответе — последняя строка.
    """
    by_key = {(r.ticker, r.report_date): r.model_dump() for r in reports}
    rows = list(by_key.values())
    if not rows:
        return 0
    statement = insert(orm.EarningsTrack).values(rows)
    excluded = statement.excluded
    statement = statement.on_conflict_do_update(
        index_elements=["ticker", "report_date"],
        set_={
            "report_time": func.coalesce(excluded.report_time, orm.EarningsTrack.report_time),
            "fiscal_period_end": excluded.fiscal_period_end,
            "eps_consensus": excluded.eps_consensus,
            "eps_actual": excluded.eps_actual,
            "eps_surprise_pct": excluded.eps_surprise_pct,
            "updated_at": func.now(),
        },
    )
    session.execute(statement)
    return len(rows)


def has_reported_eps(session: Session, ticker: str) -> bool:
    """Загружена ли история EPS: есть отчёт с фактом EPS и концом фискального квартала."""
    found = session.scalar(
        select(orm.EarningsTrack.id)
        .where(
            orm.EarningsTrack.ticker == ticker,
            orm.EarningsTrack.eps_actual.is_not(None),
            orm.EarningsTrack.fiscal_period_end.is_not(None),
        )
        .limit(1)
    )
    return found is not None


def earnings_dates(
    session: Session, ticker: str, since: date
) -> list[tuple[date, ReportTime | None]]:
    """Даты отчётов компании из earnings_track начиная с since, по возрастанию."""
    rows = session.execute(
        select(orm.EarningsTrack.report_date, orm.EarningsTrack.report_time)
        .where(orm.EarningsTrack.ticker == ticker, orm.EarningsTrack.report_date >= since)
        .order_by(orm.EarningsTrack.report_date)
    ).all()
    return [(r.report_date, _report_time(r.report_time)) for r in rows]


ARCHIVE_FIELDS = frozenset({"rev_actual", "actual_move", "move_ratio"})


def earnings_history(session: Session, ticker: str, since: date) -> list[EarningsTrack]:
    """Отчёты компании из earnings_track начиная с since, по возрастанию даты."""
    rows = session.scalars(
        select(orm.EarningsTrack)
        .where(orm.EarningsTrack.ticker == ticker, orm.EarningsTrack.report_date >= since)
        .order_by(orm.EarningsTrack.report_date)
    ).all()
    return [EarningsTrack.model_validate(r, from_attributes=True) for r in rows]


def update_earnings(
    session: Session, ticker: str, report_date: date, values: dict[str, float | None]
) -> None:
    """Поля архива прошлого отчёта (T11): выручка-факт, фактическое движение, move_ratio."""
    unknown = set(values) - ARCHIVE_FIELDS
    if unknown:
        raise ValueError(f"not archive fields: {sorted(unknown)}")
    session.execute(
        update(orm.EarningsTrack)
        .where(orm.EarningsTrack.ticker == ticker, orm.EarningsTrack.report_date == report_date)
        .values(**values, updated_at=func.now())
    )


def save_feature_snapshot(session: Session, snapshot: FeatureSnapshot) -> bool:
    """Признаки агента на стадии события. Версия агента — часть ключа: повтор не перезаписывает."""
    statement = (
        insert(orm.FeatureSnapshot)
        .values(snapshot.model_dump())
        .on_conflict_do_nothing(index_elements=["event_id", "stage", "agent_id", "agent_version"])
        .returning(orm.FeatureSnapshot.event_id)
    )
    return session.execute(statement).scalar_one_or_none() is not None


def save_sector_summary(session: Session, summary: SectorSummary) -> None:
    """Итог агента «Сектор» на дату: повтор за ту же дату обновляет строку, а не дублирует."""
    row = session.scalars(
        select(orm.SectorSummary).where(
            orm.SectorSummary.sector_id == summary.sector_id,
            orm.SectorSummary.as_of == summary.as_of,
        )
    ).first()
    values = summary.model_dump(exclude={"id"})
    if row is None:
        session.add(orm.SectorSummary(**values))
    else:
        for name, value in values.items():
            setattr(row, name, value)
    session.flush()


def set_date_check(
    session: Session,
    ticker: str,
    report_date: date,
    filing_date: date | None,
    status: DateCheckStatus,
) -> None:
    """Результат сверки даты отчёта с 8-K (T11); mismatch бэктест исключает."""
    session.execute(
        update(orm.EarningsTrack)
        .where(orm.EarningsTrack.ticker == ticker, orm.EarningsTrack.report_date == report_date)
        .values(sec_filing_date=filing_date, date_check=status, updated_at=func.now())
    )


def set_implied_move(session: Session, ticker: str, report_date: date, move: float) -> None:
    """Ожидаемое движение прошлого отчёта (T10)."""
    session.execute(
        update(orm.EarningsTrack)
        .where(orm.EarningsTrack.ticker == ticker, orm.EarningsTrack.report_date == report_date)
        .values(implied_move=move, updated_at=func.now())
    )


def save_option_minute_bars(session: Session, bars: Iterable[OptionMinuteBar]) -> int:
    """Минутные цены контрактов. Повтор обновляет значения."""
    rows = [b.model_dump() for b in bars]
    if not rows:
        return 0
    statement = insert(orm.OptionMinuteBar).values(rows)
    updated = ("open", "high", "low", "close", "volume", "vwap", "transactions")
    statement = statement.on_conflict_do_update(
        index_elements=["option_ticker", "minute"],
        set_={**{c: statement.excluded[c] for c in updated}, "updated_at": func.now()},
    )
    session.execute(statement)
    return len(rows)


def option_minute_bars(
    session: Session, tickers: Iterable[str], start: datetime, end: datetime
) -> dict[str, list[OptionMinuteBar]]:
    """Минутные цены контрактов в [start, end), по возрастанию времени."""
    rows = session.scalars(
        select(orm.OptionMinuteBar)
        .where(
            orm.OptionMinuteBar.option_ticker.in_(list(tickers)),
            orm.OptionMinuteBar.minute >= start,
            orm.OptionMinuteBar.minute < end,
        )
        .order_by(orm.OptionMinuteBar.minute)
    ).all()
    result: dict[str, list[OptionMinuteBar]] = {}
    for row in rows:
        bar = OptionMinuteBar.model_validate(row, from_attributes=True)
        result.setdefault(bar.option_ticker, []).append(bar)
    return result


def option_bars_on(session: Session, underlying: str, day: date) -> list[OptionDailyBar]:
    """Архивные цены контрактов базового актива за день."""
    rows = session.scalars(
        select(orm.OptionDailyBar).where(
            orm.OptionDailyBar.underlying == underlying, orm.OptionDailyBar.day == day
        )
    ).all()
    return [OptionDailyBar.model_validate(r, from_attributes=True) for r in rows]


REPORT_TIMES: dict[str, ReportTime] = {"BMO": "BMO", "AMC": "AMC", "DURING": "DURING"}


def _report_time(value: str | None) -> ReportTime | None:
    if value is None:
        return None
    if value not in REPORT_TIMES:
        raise ValueError(f"unexpected report_time in earnings_track: {value}")
    return REPORT_TIMES[value]


def sync_universe(session: Session, universe: Universe) -> None:
    """Сектора, компании и граф информаторов из config/universe.yaml в БД.

    Конфиг — источник названий и состава; оценки strength / lag_days по архиву (T11) не затираются.
    """
    sectors = [
        {
            "id": s.id,
            "name": s.name,
            "key_metrics": s.key_metrics,
            "macro_sensitivity": s.macro_sensitivity,
        }
        for s in universe.sectors
    ]
    statement = insert(orm.Sector).values(sectors)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["id"],
            set_={
                "name": statement.excluded.name,
                "key_metrics": statement.excluded.key_metrics,
                "macro_sensitivity": statement.excluded.macro_sensitivity,
                "updated_at": func.now(),
            },
        )
    )
    companies = [
        {"ticker": c.ticker, "sector_id": s.id, "name": c.name}
        for s in universe.sectors
        for c in s.companies
    ]
    statement = insert(orm.Company).values(companies)
    session.execute(
        statement.on_conflict_do_update(
            index_elements=["ticker"],
            set_={
                "sector_id": statement.excluded.sector_id,
                "name": statement.excluded.name,
                "updated_at": func.now(),
            },
        )
    )
    if universe.peer_edges:
        edges = [
            {"from_ticker": e.from_ticker, "to_ticker": e.to_ticker} for e in universe.peer_edges
        ]
        session.execute(insert(orm.PeerEdge).values(edges).on_conflict_do_nothing())


def save_event_jobs(session: Session, jobs: Iterable[EventJob]) -> int:
    """План задач события. Повтор обновляет время, а не дублирует; выполненные не трогаются."""
    rows = [j.model_dump() for j in jobs]
    if not rows:
        return 0
    statement = insert(orm.EventJob).values(rows)
    statement = statement.on_conflict_do_update(
        index_elements=["event_id", "stage", "job"],
        set_={
            "kind": statement.excluded.kind,
            "run_at": statement.excluded.run_at,
            "outside_session": statement.excluded.outside_session,
            "updated_at": func.now(),
        },
        where=orm.EventJob.status == "planned",
    )
    session.execute(statement)
    return len(rows)
