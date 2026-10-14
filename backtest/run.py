"""Бэктест стратегий на move_ratio (T12a): `make backtest` → reports/backtest_<дата>.md.

Данные — только из архива (earnings_track, option_daily_bar, option_minute_bar) и закрытия
акций Massive. Перед запуском — `make build-archive` и `make backtest-data`.
Без CostModel бэктест не запускается (SPEC §17 п.3).
"""

import logging
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy.orm import Session

from adapters.broker.factory import create_cost_model
from adapters.cache import RedisCache
from adapters.errors import DataError
from adapters.fred.client import FredClient, fred_api_key
from adapters.massive.client import MassiveClient, massive_api_key
from adapters.massive.history import (
    HistoricalStraddle,
    spot_on,
    stock_closes,
    straddle_from_bars,
)
from adapters.massive.symbols import daily_bars
from backtest.exit_data import exit_window
from backtest.mode_c_run import run_mode_c
from backtest.option_history import STOCK_PADDING_DAYS, StockBarsSource
from backtest.report import render
from backtest.result import BacktestResult
from backtest.signals import Construction, Signal, condor_strikes, signals
from backtest.simulate import Leg, Trade, simulate
from core.config import AppConfig, ConfigError, load_config
from core.config.sources import MassiveHistory
from core.config.thresholds import CondorStopBasis, Thresholds
from core.db.session import create_db_engine, database_url
from core.db.store import earnings_history, option_bars_on, option_minute_bars
from core.domain.options import OptionDailyBar
from core.risk.black_swan import Level, levels
from core.session_guard import to_et
from execution.costs import BrokerCostModel, CostModel

logger = logging.getLogger(__name__)


def run_backtest(
    db: Session,
    tickers: Sequence[str],
    *,
    thresholds: Thresholds,
    history: MassiveHistory,
    stocks: StockBarsSource,
    costs: CostModel | None,
    today: date,
) -> BacktestResult:
    """Сделки по всем сигналам компаний; без модели издержек — ValueError."""
    if costs is None:
        raise ValueError("backtest requires a CostModel (SPEC §17 п.3)")
    since = today - timedelta(days=history.archive_days)
    bt = thresholds.backtest
    result = BacktestResult(since=since, until=today)
    for ticker in tickers:
        found = signals(
            ticker,
            earnings_history(db, ticker, date.min),
            since=since,
            today=today,
            settings=thresholds.backtest,
            constructions=thresholds.constructions,
        )
        if not found:
            continue
        result.tickers += 1
        for item in found:
            result.signals[item.construction or item.reason or "none"] += 1
        active = [s for s in found if s.construction is not None]
        if not active:
            continue
        bars = stocks.aggregates(
            ticker,
            1,
            "day",
            active[0].days.pre - timedelta(days=STOCK_PADDING_DAYS),
            active[-1].days.reaction,
            adjusted=False,
        )
        closes = stock_closes(bars)
        for item in active:
            if item.construction is None:
                continue
            variants: list[CondorStopBasis | None] = (
                [None] if item.construction == "straddle" else list(bt.compare_condor_stops)
            )
            for i, variant in enumerate(variants):
                outcome = _trade(
                    db, item, item.construction, closes, thresholds, history, costs, variant
                )
                if isinstance(outcome, Trade):
                    result.trades.append(outcome)
                elif i == 0:  # пропуск считается один раз на событие, не на вариант
                    result.skipped[f"{item.construction}: {outcome}"] += 1
    return result


def _trade(
    db: Session,
    item: Signal,
    construction: Construction,
    closes: dict[date, float],
    thresholds: Thresholds,
    history: MassiveHistory,
    costs: CostModel,
    condor_stop: CondorStopBasis | None = None,
) -> Trade | str:
    try:
        spot = spot_on(closes, item.ticker, item.days)
        archived = option_bars_on(db, item.ticker, item.days.pre)
        straddle = straddle_from_bars(
            item.ticker, item.days, spot, archived, history.risk_free_rate
        )
    except DataError:
        return "no_entry_price"
    width: float | None = None
    if construction == "straddle":
        legs = [
            Leg(straddle.call_ticker, 1, straddle.call_close),
            Leg(straddle.put_ticker, 1, straddle.put_close),
        ]
    else:
        condor = _condor_legs(item, spot, straddle, archived, thresholds)
        if condor is None:
            return "no_condor_legs"
        legs, width = condor
    start, end = exit_window(item.days.reaction, thresholds.backtest.exit_time_et)
    minutes = option_minute_bars(db, [leg.ticker for leg in legs], start, end)
    return simulate(
        item.ticker,
        item.days.report_date,
        construction,
        legs,
        minutes,
        rules=thresholds.constructions,
        costs=costs,
        session_open=start,
        open_slippage_minutes=thresholds.backtest.open_slippage_minutes,
        width=width,
        condor_stop=condor_stop,
        entry_on=item.days.pre,  # вход по закрытию накануне реакции
    )


def _condor_legs(
    item: Signal,
    spot: float,
    straddle: HistoricalStraddle,
    archived: Sequence[OptionDailyBar],
    thresholds: Thresholds,
) -> tuple[list[Leg], float] | None:
    """Ноги кондора из архива за день накануне (их скачал `make backtest-data`)."""
    same = [b for b in archived if b.expiration == straddle.expiration]
    calls = {b.strike: b for b in same if b.option_type == "call"}
    puts = {b.strike: b for b in same if b.option_type == "put"}
    rules = thresholds.constructions.iron_condor
    strikes = condor_strikes(
        sorted(calls),
        sorted(puts),
        spot,
        item.implied_move,
        rules.short_implied_moves,
        rules.wing_implied_moves,
    )
    if strikes is None:
        return None
    legs = [
        Leg(puts[strikes.long_put].option_ticker, 1, puts[strikes.long_put].close),
        Leg(puts[strikes.short_put].option_ticker, -1, puts[strikes.short_put].close),
        Leg(calls[strikes.short_call].option_ticker, -1, calls[strikes.short_call].close),
        Leg(calls[strikes.long_call].option_ticker, 1, calls[strikes.long_call].close),
    ]
    return legs, strikes.width


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover
    """`make backtest`: вся вселенная, отчёт в reports/backtest_<дата>.md."""
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    config = load_config()
    today = to_et(datetime.now(UTC)).date()
    cache = RedisCache.from_env(config.sources.redis.timeout_seconds)
    stocks = MassiveClient.create(config.sources.massive, massive_api_key(), cache)
    with Session(create_db_engine(database_url())) as db:
        result = run_backtest(
            db,
            config.universe.tickers(),
            thresholds=config.thresholds,
            history=config.sources.massive.history,
            stocks=stocks,
            costs=create_cost_model(config.broker),
            today=today,
        )
        stock_costs = config.broker.selected_costs.model_copy(
            update={"assumed_spread_stock": config.thresholds.backtest.mode_c.assumed_spread_stock}
        )
        mode_c = run_mode_c(
            db,
            config.universe.tickers(),
            thresholds=config.thresholds,
            history=config.sources.massive.history,
            stocks=stocks,
            costs=BrokerCostModel(stock_costs),
            capital=config.thresholds.capital.module_usd,
            today=today,
        )
    swan = _black_swan_levels(config, stocks, cache, today)
    text = render(result, config.thresholds, config.broker.selected_costs, mode_c, swan)
    path = Path(__file__).resolve().parents[1] / "reports" / f"backtest_{today:%Y-%m-%d}.md"
    path.parent.mkdir(exist_ok=True)
    path.write_text(text, encoding="utf-8")
    logger.info(
        "Сделок на move_ratio: %d, режима C: %d. Отчёт: %s",
        len(result.trades),
        len(mode_c.trades),
        path,
    )
    return 0


def _black_swan_levels(
    config: AppConfig, stocks: MassiveClient, cache: RedisCache, today: date
) -> dict[date, Level] | None:  # pragma: no cover
    """Уровни Black Swan за глубину цен акций: VIX — FRED, SPY — Massive. Нет ключа FRED — None."""
    since = today - timedelta(days=config.sources.massive.history.stock_history_days)
    try:
        fred = FredClient.create(config.sources.fred, fred_api_key(), cache)
    except ConfigError as exc:
        logger.warning("Black Swan пропущен: %s", exc)
        return None
    vix = {
        o.date: o.value for o in fred.observations("VIXCLS", since, today) if o.value is not None
    }
    spy = stock_closes(daily_bars(stocks, "SPY", since, today))
    return levels(vix, spy, config.thresholds.risk_limits.black_swan)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
