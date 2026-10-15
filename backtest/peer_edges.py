"""Связи «кто кому сигналит» по архиву (E6, universe.yaml peer_edges: strength / lag_days — T11).

Пара отчётов — отчёт «информатора» (from) и ближайший после него отчёт ведомой компании (to)
не позже `max_lag_days`, только за последние `lookback_days` (история Alpha Vantage уходит на
десятилетия, выбросы 2008 года раздували корреляцию). lag_days — медиана дней между ними;
strength — ранговая корреляция (Спирмен, устойчива к выбросам) сюрпризов EPS, от `min_pairs` пар,
иначе пусто. Пишется в peer_edge; синхронизация вселенной оценки не затирает.
"""

import statistics
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.db import models as orm

MAX_LAG_DAYS = 45
MIN_PAIRS = 6
LOOKBACK_DAYS = 1825  # 5 лет — как у стартовых моделей (models.prior_lookback_days)


@dataclass(frozen=True)
class EdgeEstimate:
    from_ticker: str
    to_ticker: str
    pairs: int
    lag_days: int | None
    strength: float | None


def estimate_peer_edges(
    session: Session, today: date, lookback_days: int = LOOKBACK_DAYS
) -> list[EdgeEstimate]:
    """Оценить и записать strength / lag_days у всех связей peer_edge."""
    since = today - timedelta(days=lookback_days)
    out = []
    for edge in session.scalars(select(orm.PeerEdge)):
        pairs = _pairs(session, edge.from_ticker, edge.to_ticker, since)
        lags = [lag for lag, _, _ in pairs]
        surprises = [(a, b) for _, a, b in pairs if a is not None and b is not None]
        strength = None
        if len(surprises) >= MIN_PAIRS:
            xs, ys = zip(*surprises, strict=True)
            try:
                strength = round(statistics.correlation(xs, ys, method="ranked"), 3)
            except statistics.StatisticsError:  # постоянный ряд — корреляции нет
                strength = None
        edge.lag_days = round(statistics.median(lags)) if lags else None
        edge.strength = strength
        out.append(
            EdgeEstimate(edge.from_ticker, edge.to_ticker, len(pairs), edge.lag_days, strength)
        )
    session.flush()
    return out


def _pairs(
    session: Session, from_ticker: str, to_ticker: str, since: date
) -> list[tuple[int, float | None, float | None]]:
    def reports(ticker: str) -> list[tuple[date, float | None]]:
        return [
            (r.report_date, r.eps_surprise_pct)
            for r in session.scalars(
                select(orm.EarningsTrack)
                .where(orm.EarningsTrack.ticker == ticker, orm.EarningsTrack.report_date >= since)
                .order_by(orm.EarningsTrack.report_date)
            )
        ]

    targets = reports(to_ticker)
    out = []
    for day, surprise in reports(from_ticker):
        after = [(d, s) for d, s in targets if 0 <= (d - day).days <= MAX_LAG_DAYS]
        if after:
            target_day, target_surprise = after[0]
            out.append(((target_day - day).days, surprise, target_surprise))
    return out
