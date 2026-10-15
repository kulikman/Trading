"""Ежедневное пополнение архива прошлых отчётов (T12c): планировщик, будни 18:30 ET.

Берёт отчёты из календаря событий (таблица event), у которых день реакции пришёлся на последние
archive.lookback_trading_days торговых дней — пропущенный вечер (сервис не работал) наверстается.
По каждой такой компании:
1. история отчётов Alpha Vantage перезапрашивается, только если нового отчёта в архиве ещё нет
   (лимит 25 запросов в день);
2. сборка архива: цены опционов и implied move, фактическое движение, выручка SEC, сверка с 8-K;
3. данные выхода для бэктеста (минутные цены, ноги кондора) — только по свежим отчётам;
4. теневые сделки (T16) и paper-сделки — когда цены выхода уже скачаны.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.alphavantage.client import AlphaVantageClient, alphavantage_api_key
from adapters.broker.factory import create_cost_model
from adapters.cache import RedisCache
from adapters.edgar.client import EdgarClient, sec_user_agent
from adapters.massive.client import MassiveClient, massive_api_key
from adapters.massive.history import EventDays
from backtest.build_archive import ArchiveBuilder, TickerArchive
from backtest.exit_data import ExitDataLoader, ExitDataReport
from backtest.option_history import OptionHistoryLoader
from core.config import AppConfig, load_config
from core.db import models as orm
from core.domain.types import ReportTime
from core.error_log import logged_job
from core.scheduler.jobs import engine
from core.session_guard import is_trading_day, previous_trading_day, to_et
from execution.attribution import MassiveSpots
from execution.paper import PaperBook, PaperRunResult
from learning.shadow import ShadowCalculator, ShadowRunResult

logger = logging.getLogger(__name__)

DATE_MATCH_DAYS = (
    3  # отчёт календаря и строка истории Alpha Vantage — тот же отчёт в пределах 3 дней
)


class ArchiveStep(Protocol):
    def build(self, session: Session, ticker: str, *, refresh_dates: bool = False) -> TickerArchive:
        """Сборка архива по компании."""


class ShadowStep(Protocol):
    def run(self, session: Session, today: date, retry_since: date) -> ShadowRunResult:
        """Теневые сделки закрывшихся событий."""


class PaperStep(Protocol):
    def run(self, session: Session, today: date, retry_since: date) -> PaperRunResult:
        """Paper-сделки закрывшихся событий."""


class ExitStep(Protocol):
    def load(self, db: Session, ticker: str, *, since: date | None = None) -> ExitDataReport:
        """Данные выхода по сигналам компании."""


@dataclass(frozen=True)
class DueReport:
    ticker: str
    report_date: date
    needs_dates: bool  # в архиве ещё нет этого отчёта с фактом EPS


@dataclass
class DailyArchiveResult:
    due: list[DueReport] = field(default_factory=list)
    archives: list[TickerArchive] = field(default_factory=list)
    exits: list[ExitDataReport] = field(default_factory=list)
    shadows: ShadowRunResult | None = None
    paper: PaperRunResult | None = None


def due_reports(
    session: Session, today: date, lookback_trading_days: int, tickers: set[str]
) -> list[DueReport]:
    """Отчёты календаря с днём реакции в последних lookback торговых днях (не позже вчера)."""
    oldest = lookback_start(today, lookback_trading_days)
    events = session.execute(
        select(orm.Event.ticker, orm.Event.report_date, orm.Event.report_time).where(
            orm.Event.report_date >= oldest - timedelta(days=DATE_MATCH_DAYS),
            orm.Event.report_date < today,
        )
    ).all()
    due = []
    for ticker, report_date, report_time in sorted(events):
        reaction = EventDays.of(report_date, _report_time(report_time)).reaction
        if ticker not in tickers or not oldest <= reaction < today:
            continue
        due.append(DueReport(ticker, report_date, not _archived(session, ticker, report_date)))
    return due


def lookback_start(today: date, lookback_trading_days: int) -> date:
    """Первый день окна: lookback торговых дней назад."""
    oldest = today
    for _ in range(lookback_trading_days):
        oldest = previous_trading_day(oldest)
    return oldest


class DailyArchive:
    def __init__(
        self,
        *,
        builder: ArchiveStep,
        exits: ExitStep,
        lookback_trading_days: int,
        tickers: set[str],
        shadows: ShadowStep | None = None,
        paper: PaperStep | None = None,
    ) -> None:
        self._builder = builder
        self._exits = exits
        self._shadows = shadows
        self._paper = paper
        self._lookback = lookback_trading_days
        self._tickers = tickers

    def run(self, session: Session, today: date) -> DailyArchiveResult:
        """Один вечерний прогон. Повтор не дублирует данные и не тратит лишних запросов."""
        result = DailyArchiveResult(due=due_reports(session, today, self._lookback, self._tickers))
        by_ticker: dict[str, list[DueReport]] = {}
        for item in result.due:
            by_ticker.setdefault(item.ticker, []).append(item)
        for ticker, items in sorted(by_ticker.items()):
            refresh = any(i.needs_dates for i in items)
            result.archives.append(self._builder.build(session, ticker, refresh_dates=refresh))
            since = min(i.report_date for i in items)
            result.exits.append(self._exits.load(session, ticker, since=since))
        retry_since = lookback_start(today, self._lookback)
        if self._shadows is not None:
            result.shadows = self._shadows.run(session, today, retry_since)
        if self._paper is not None:
            result.paper = self._paper.run(session, today, retry_since)
        logger.info(
            "daily archive",
            extra={"reports": len(result.due), "tickers": len(by_ticker)},
        )
        return result


@logged_job("archive-daily", lambda: engine())
def run_daily_archive(
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    factory: Callable[[AppConfig, date], DailyArchive] | None = None,
) -> DailyArchiveResult | None:
    """Задача планировщика; в неторговый день ничего не делает."""
    today = to_et(now()).date()
    if not is_trading_day(today):
        return None
    config = load_config()
    archive = (factory or build_daily_archive)(config, today)
    with Session(engine()) as session:
        return archive.run(session, today)


def build_daily_archive(config: AppConfig, today: date) -> DailyArchive:  # pragma: no cover
    """Боевые зависимости: клиенты Massive, Alpha Vantage, SEC с кэшем Redis."""
    sources = config.sources
    cache = RedisCache.from_env(sources.redis.timeout_seconds)
    key = massive_api_key()
    options = MassiveClient.create_history(sources.massive, key, cache)
    stocks = MassiveClient.create(sources.massive, key, cache)
    loader = OptionHistoryLoader(
        options=options,
        stocks=stocks,
        earnings=AlphaVantageClient.create(sources.alphavantage, alphavantage_api_key(), cache),
        settings=sources.massive.history,
        today=today,
    )
    builder = ArchiveBuilder(
        loader=loader,
        stocks=stocks,
        sec=EdgarClient.create(sources.edgar, sec_user_agent(), cache),
        edgar=sources.edgar,
        today=today,
        predecessor_ciks=config.universe.sec_predecessor_ciks(),
    )
    exits = ExitDataLoader(
        options=options,
        stocks=stocks,
        settings=sources.massive.history,
        thresholds=config.thresholds,
        today=today,
    )
    shadows = ShadowCalculator(
        stocks=stocks,
        thresholds=config.thresholds,
        history=sources.massive.history,
        costs=create_cost_model(config.broker),
    )
    return DailyArchive(
        builder=builder,
        exits=exits,
        shadows=shadows,
        paper=PaperBook(
            shadows,
            config.thresholds,
            spots=MassiveSpots(stocks),
            rate=sources.massive.history.risk_free_rate,
        ),
        lookback_trading_days=config.schedule.archive.lookback_trading_days,
        tickers=set(config.universe.tickers()),
    )


def _archived(session: Session, ticker: str, report_date: date) -> bool:
    found = session.scalar(
        select(orm.EarningsTrack.id)
        .where(
            orm.EarningsTrack.ticker == ticker,
            orm.EarningsTrack.report_date >= report_date - timedelta(days=DATE_MATCH_DAYS),
            orm.EarningsTrack.report_date <= report_date + timedelta(days=DATE_MATCH_DAYS),
            orm.EarningsTrack.eps_actual.is_not(None),
        )
        .limit(1)
    )
    return found is not None


REPORT_TIMES: dict[str, ReportTime] = {"BMO": "BMO", "AMC": "AMC", "DURING": "DURING"}


def _report_time(value: str | None) -> ReportTime | None:
    return REPORT_TIMES.get(value) if value is not None else None


def main() -> int:  # pragma: no cover
    """`make run-archive-daily`: разовый прогон вне расписания."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    result = run_daily_archive()
    if result is None:
        logger.info("Сегодня неторговый день — архив не пополнялся.")
        return 0
    logger.info(
        "Отчётов к пополнению: %d (%s)",
        len(result.due),
        ", ".join(f"{d.ticker} {d.report_date:%d.%m}" for d in result.due) or "нет",
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
