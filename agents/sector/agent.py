"""Агент «Сектор» (SPEC §8): peer_surprise_mean, trend, confidence, sector_momentum_30d.

Сюрпризы — отчёты других компаний сектора за последние season_window_days дней (архив
earnings_track, без строк с датой под сомнением). «Тренд сектора» (решение заказчика 14.10.2026):
знак среднего сюрприза EPS, если отчиталось ≥ min_peers и он по модулю > min_abs_surprise, иначе 0;
confidence — доля отчитавшихся с сюрпризом того же знака. Momentum — средняя доходность компаний
сектора за momentum_days на закрытии перед запуском. Итог пишется и в sector_summary.
"""

import statistics
from collections.abc import Sequence
from datetime import date, timedelta

from pydantic import BaseModel
from sqlalchemy import select

from adapters.errors import DataError
from adapters.massive.history import stock_closes
from adapters.massive.symbols import StockHistorySource, daily_bars
from core.config.thresholds import SectorAgent
from core.config.universe import Universe
from core.db import models as orm
from core.db.store import save_sector_summary
from core.domain.market import SectorSummary
from core.domain.types import Direction
from core.registry.protocols import EventContext, Trigger
from core.session_guard import to_et

STAGES = ("T-14", "T-3")


class SectorFeatures(BaseModel):
    peer_surprise_mean: float | None = None
    peers_reported: int = 0
    trend: Direction = 0
    confidence: float | None = None
    sector_momentum_30d: float | None = None


class SectorAgentPlugin:
    id = "sector"
    version = "0.1.0"
    triggers: Sequence[Trigger] = tuple(Trigger("stage", s) for s in STAGES)
    reads: Sequence[str] = ("archive:earnings_track", "massive:daily_bars")
    output_schema = SectorFeatures

    def __init__(
        self, stocks: StockHistorySource, universe: Universe, settings: SectorAgent
    ) -> None:
        self._stocks = stocks
        self._universe = universe
        self._settings = settings

    def run(self, ctx: EventContext) -> SectorFeatures:
        if ctx.session is None:
            raise DataError("archive", "sector agent needs the archive session")
        day = to_et(ctx.as_of).date()
        sector = self._universe.sector_of(ctx.ticker)
        peers = [c.ticker for c in sector.companies if c.ticker != ctx.ticker]
        rows = ctx.session.execute(
            select(orm.EarningsTrack.ticker, orm.EarningsTrack.eps_surprise_pct)
            .where(
                orm.EarningsTrack.ticker.in_(peers),
                orm.EarningsTrack.report_date
                >= day - timedelta(days=self._settings.season_window_days),
                orm.EarningsTrack.report_date < day,
                orm.EarningsTrack.eps_surprise_pct.is_not(None),
                orm.EarningsTrack.date_check.is_distinct_from("mismatch"),
            )
            .order_by(orm.EarningsTrack.report_date)
        ).all()
        # последний отчёт каждой компании; сюрприз в архиве — в процентах
        latest = {ticker: surprise / 100 for ticker, surprise in rows if surprise is not None}
        surprises = list(latest.values())
        mean = statistics.fmean(surprises) if surprises else None
        trend = self._trend(mean, len(surprises))
        confidence = (
            sum((s > 0) == (trend > 0) for s in surprises if s != 0) / len(surprises)
            if trend != 0
            else None
        )
        features = SectorFeatures(
            peer_surprise_mean=mean,
            peers_reported=len(surprises),
            trend=trend,
            confidence=confidence,
            sector_momentum_30d=self._momentum([c.ticker for c in sector.companies], day),
        )
        save_sector_summary(
            ctx.session,
            SectorSummary(
                sector_id=sector.id,
                as_of=day,
                trend=features.trend,
                confidence=features.confidence,
                peer_surprise_mean=features.peer_surprise_mean,
                sector_momentum_30d=features.sector_momentum_30d,
            ),
        )
        return features

    def _trend(self, mean: float | None, count: int) -> Direction:
        if mean is None or count < self._settings.min_peers:
            return 0
        if abs(mean) <= self._settings.min_abs_surprise:
            return 0
        return 1 if mean > 0 else -1

    def _momentum(self, tickers: Sequence[str], day: date) -> float | None:
        """Средняя доходность компаний сектора за momentum_days на закрытии перед day."""
        window = timedelta(days=self._settings.momentum_days)
        returns = []
        for ticker in tickers:
            closes = stock_closes(daily_bars(self._stocks, ticker, day - window * 2, day))
            before = sorted(d for d in closes if d < day)
            if not before:
                continue
            last = before[-1]
            anchor = [d for d in before if d <= last - window]
            if anchor:
                returns.append(closes[last] / closes[anchor[-1]] - 1)
        return statistics.fmean(returns) if returns else None
