"""Уровень Black Swan по дням (E2d): ежедневная задача market-daily, 06:05 ET.

Агент «Макро» считает уровень только по задачам событий — в день без событий уровень на плашке
«РЫНОК» и в решениях мог устареть. Задача пересчитывает уровень на закрытии каждого торгового дня
окна `agents.macro.lookback_days` (то же правило, что у агента) и пишет его в market_level.
Решение берёт уровень закрытия накануне (`core.risk.market.market_level_before`), агент — запасной
путь.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from adapters.cache import RedisCache
from adapters.fred.client import FredClient, FredSource, fred_api_key
from adapters.massive.client import MassiveClient, massive_api_key
from adapters.massive.history import stock_closes
from adapters.massive.symbols import StockHistorySource, daily_bars
from agents.macro.agent import VIX_SERIES, observed_values
from core.config import AppConfig, load_config
from core.config.thresholds import Thresholds
from core.db import models as orm
from core.error_log import logged_job
from core.risk.black_swan import levels
from core.scheduler.jobs import engine
from core.session_guard import is_trading_day, previous_trading_day, to_et


def update_market_level(
    session: Session,
    fred: FredSource,
    stocks: StockHistorySource,
    thresholds: Thresholds,
    today: date,
) -> orm.MarketLevelDay | None:
    """Уровни дней окна до закрытия накануне; возвращает строку последнего дня (нет SPY — None)."""
    close_day = previous_trading_day(today)
    start = close_day - timedelta(days=thresholds.agents.macro.lookback_days)
    vix = observed_values(fred.observations(VIX_SERIES, start, close_day))
    spy = stock_closes(daily_bars(stocks, "SPY", start, close_day))
    by_day = levels(vix, spy, thresholds.risk_limits.black_swan)
    for day, level in by_day.items():
        values = {"level": level, "vix": vix.get(day), "spy": spy.get(day)}
        session.execute(
            insert(orm.MarketLevelDay)
            .values(day=day, **values)
            .on_conflict_do_update(index_elements=["day"], set_=values)
        )
    session.flush()
    return session.get(orm.MarketLevelDay, close_day) if close_day in by_day else None


def build_sources(config: AppConfig) -> tuple[FredSource, StockHistorySource]:  # pragma: no cover
    cache = RedisCache.from_env(config.sources.redis.timeout_seconds)
    return (
        FredClient.create(config.sources.fred, fred_api_key(), cache),
        MassiveClient.create(config.sources.massive, massive_api_key(), cache),
    )


@logged_job("market-daily", lambda: engine())
def run_market_level(
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    sources_factory: Callable[[AppConfig], tuple[FredSource, StockHistorySource]] = build_sources,
) -> orm.MarketLevelDay | None:
    """Задача планировщика; в неторговый день ничего не делает."""
    today = to_et(now()).date()
    if not is_trading_day(today):
        return None
    config = load_config()
    fred, stocks = sources_factory(config)
    with Session(engine()) as session, session.begin():
        return update_market_level(session, fred, stocks, config.thresholds, today)
