from datetime import date, timedelta

import pytest
from sqlalchemy.orm import Session

from backtest.liquidity import option_liquidity, update_options_liquid
from backtest.peer_edges import estimate_peer_edges
from core.config import load_config
from core.db import models as orm
from core.db.store import save_reported_earnings, sync_universe
from core.domain.earnings import ReportedEarnings

CONFIG = load_config()


def bar(ticker: str, day: date, expiration: date, kind: str, volume: float) -> orm.OptionDailyBar:
    return orm.OptionDailyBar(
        option_ticker=f"O:{ticker}{expiration:%y%m%d}{kind[0].upper()}00100000-{day}",
        day=day,
        underlying=ticker,
        expiration=expiration,
        strike=100.0,
        option_type=kind,
        open=1,
        high=1,
        low=1,
        close=1,
        volume=volume,
        vwap=1,
        transactions=1,
    )


def test_liquidity_flag_from_archive(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    for i in range(4):
        day = date(2026, 1, 13) + timedelta(days=91 * i)
        weekly = day + timedelta(days=(4 - day.weekday()) % 7 or 7)  # ближайшая пятница
        session.add_all(
            [bar("NFLX", day, weekly, "call", 400), bar("NFLX", day, weekly, "put", 300)]
        )
        monthly = date(2026, 1, 16) + timedelta(days=91 * i)
        session.add_all([bar("DE", day, monthly, "call", 20), bar("DE", day, monthly, "put", 10)])
    session.flush()
    nflx = option_liquidity(session, "NFLX")
    assert (nflx.median_volume, nflx.days) == (700, 4)
    found = {f.ticker: f for f in update_options_liquid(session, ["NFLX", "DE", "TSLA"], 500)}
    assert found["TSLA"].median_volume is None
    flags = {
        t: getattr(session.get(orm.Company, t), "options_liquid", None)
        for t in ("NFLX", "DE", "TSLA")
    }
    assert flags == {"NFLX": found["NFLX"].has_weeklies, "DE": False, "TSLA": None}


def test_peer_edge_estimates(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    edge = CONFIG.universe.peer_edges[0]
    rows = []
    for i in range(7):
        start = date(2024, 1, 10) + timedelta(days=91 * i)
        surprise = float(i - 3)
        rows += [
            ReportedEarnings(
                ticker=edge.from_ticker,
                report_date=start,
                fiscal_period_end=start - timedelta(days=10),
                eps_surprise_pct=surprise,
            ),
            ReportedEarnings(
                ticker=edge.to_ticker,
                report_date=start + timedelta(days=2),
                fiscal_period_end=start - timedelta(days=10),
                eps_surprise_pct=surprise * 2,
            ),
        ]
    save_reported_earnings(session, rows)
    estimates = {
        (e.from_ticker, e.to_ticker): e for e in estimate_peer_edges(session, date(2026, 1, 1))
    }
    found = estimates[(edge.from_ticker, edge.to_ticker)]
    assert (found.pairs, found.lag_days) == (7, 2)
    assert found.strength == pytest.approx(1.0)
    stored = session.get(orm.PeerEdge, (edge.from_ticker, edge.to_ticker))
    assert stored is not None
    assert stored.lag_days == 2
    assert stored.strength == pytest.approx(1.0)


def test_peer_edges_ignore_old_reports(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    edge = CONFIG.universe.peer_edges[0]
    save_reported_earnings(
        session,
        [
            ReportedEarnings(
                ticker=edge.from_ticker,
                report_date=date(2009, 1, 15),
                fiscal_period_end=date(2008, 12, 31),
                eps_surprise_pct=-80.0,
            ),
            ReportedEarnings(
                ticker=edge.to_ticker,
                report_date=date(2009, 1, 17),
                fiscal_period_end=date(2008, 12, 31),
                eps_surprise_pct=-90.0,
            ),
        ],
    )
    found = {
        (e.from_ticker, e.to_ticker): e for e in estimate_peer_edges(session, date(2026, 10, 15))
    }
    assert found[(edge.from_ticker, edge.to_ticker)].pairs == 0  # 2009 год — за пределами 5 лет
