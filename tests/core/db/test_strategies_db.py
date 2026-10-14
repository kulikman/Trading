from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from sqlalchemy.orm import Session

from adapters.massive.models import Bar, TickerChange
from core.config import load_config
from core.db.store import save_reported_earnings, sync_universe, update_earnings
from core.domain.earnings import ReportedEarnings
from core.registry.protocols import DecisionContext, EventContext, Proposal, Skip
from core.session_guard import ET, previous_trading_day
from execution.costs import BrokerCostModel
from strategies.iron_condor.strategy import IronCondorStrategy
from strategies.mode_a.strategy import ModeAStrategy
from strategies.mode_b.strategy import ModeBStrategy
from strategies.straddle.strategy import StraddleStrategy

CONFIG = load_config()
THRESHOLDS = CONFIG.thresholds
COSTS = BrokerCostModel(CONFIG.broker.costs["manual"])
RATE = 0.04
AS_OF = datetime(2026, 10, 19, 19, 10, tzinfo=UTC)
REPORT = date(2026, 10, 20)


class Stocks:
    """Цена 100, диапазон дня 99–101: ATR(14) = 2."""

    def aggregates(self, ticker: str, *args: Any, **kwargs: Any) -> list[Bar]:
        out, day = [], date(2026, 10, 19)
        for _ in range(40):
            day = previous_trading_day(day)
            start = datetime.combine(day, time(0), tzinfo=ET).timestamp() * 1000
            out.append(
                Bar.model_validate({"o": 100, "h": 101, "l": 99, "c": 100, "v": 1, "t": start})
            )
        return list(reversed(out))

    def ticker_changes(self, ticker: str) -> list[TickerChange]:
        return []


def archive(session: Session, moves: list[float]) -> None:
    sync_universe(session, CONFIG.universe)
    rows = [(date(2024, 10, 17) + timedelta(days=91 * i), move) for i, move in enumerate(moves)]
    save_reported_earnings(
        session,
        [
            ReportedEarnings(
                ticker="NFLX",
                report_date=d,
                report_time="AMC",
                fiscal_period_end=d - timedelta(days=20),
            )
            for d, _ in rows
        ],
    )
    for d, move in rows:
        update_earnings(session, "NFLX", d, {"actual_move": move})


def ctx(
    session: Session,
    features: dict[str, dict[str, float]],
    forecasts: dict[str, float],
    ticker: str = "NFLX",
) -> DecisionContext:
    return DecisionContext(
        event=EventContext(
            event_id=1,
            ticker=ticker,
            report_date=REPORT,
            report_time="AMC",
            stage="T-1",
            as_of=AS_OF,
            session=session,
        ),
        features=features,
        forecasts=forecasts,
    )


def strategy(cls: type) -> Any:
    return cls(Stocks(), COSTS, THRESHOLDS, RATE)


OPTIONS = {"options": {"implied_move": 0.08, "atm_iv": 0.6}}
MOVE = {"move_ratio": 0.40, "market_move": 0.36, "p_up": 0.6, "market_p_up": 0.5}


def test_straddle_by_hand(session: Session) -> None:
    archive(session, [0.12, -0.12, 0.12, -0.12])  # средний |движение| 12% / 8% = 1,5 > 1,3
    result = strategy(StraddleStrategy).evaluate(ctx(session, OPTIONS, MOVE))
    assert isinstance(result, Proposal)
    assert result.edge == pytest.approx(0.04)
    assert result.probability == 0.40
    # премия 8 (2 ноги по 4): вход — комиссия 1,30 + полспреда 12,00;
    # выход — то же + проскальзывание 0,80
    assert result.cost_fraction == pytest.approx(27.4 / (800 + 13.3))


def test_straddle_skips(session: Session) -> None:
    archive(session, [0.08, -0.08, 0.08, -0.08])  # ratio 1,0 — движения не больше ожидаемого
    assert strategy(StraddleStrategy).evaluate(ctx(session, OPTIONS, MOVE)) == Skip(
        "straddle", ["EDGE_LOW"]
    )
    assert strategy(StraddleStrategy).evaluate(ctx(session, {}, MOVE)) == Skip(
        "straddle", ["DATA_MASSIVE"]
    )


def test_iron_condor_probability_is_no_big_move(session: Session) -> None:
    archive(session, [0.04, -0.04, 0.04, -0.04])  # ratio 0,5 < 0,75
    result = strategy(IronCondorStrategy).evaluate(ctx(session, OPTIONS, MOVE))
    assert isinstance(result, Proposal)
    assert result.probability == pytest.approx(0.60)  # 1 − 0,40
    assert result.edge == pytest.approx(0.60 - 0.64)  # против эталона 1 − 0,36
    assert 0 < result.cost_fraction < 0.5
    archive(session, [])  # уже есть — ratio тот же
    high = strategy(IronCondorStrategy).evaluate(
        ctx(session, {"options": {"implied_move": 0.02, "atm_iv": 0.6}}, MOVE)
    )
    assert high == Skip("iron_condor", ["EDGE_LOW"])  # 4% / 2% = 2,0


def test_mode_a_conditions(session: Session) -> None:
    bad = {
        "positioning": {"pre_run_30d": 0.12, "pre_run_3d": 0.04},
        "macro": {"vix": 26.0},
        "sector": {"trend": -1.0},
    }
    assert strategy(ModeAStrategy).evaluate(ctx(session, bad, MOVE)) == Skip(
        "mode_a", ["PRE_RUN", "MACRO_BLOCK", "PEER_CONFLICT"]
    )
    good = {"positioning": {"pre_run_30d": 0.02, "pre_run_3d": 0.01}, "macro": {"vix": 15.0}}
    result = strategy(ModeAStrategy).evaluate(ctx(session, good, MOVE))
    assert isinstance(result, Proposal)
    assert result.edge == pytest.approx(0.1)
    # стоп 1,5 × ATR 2 = 3 на акцию; 100 акций по 100: комиссия 1, полспреда 2,50,
    # проскальзывание на выходе 10
    assert result.cost_fraction == pytest.approx((1 + 2.5 + 1 + 2.5 + 10) / 300)


def test_mode_b_direction_gates_and_size(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    bear = {"p_up": 0.4, "market_p_up": 0.5}
    conflict = strategy(ModeBStrategy).evaluate(
        ctx(session, {**OPTIONS, "sector": {"trend": 1.0}}, bear)
    )
    assert conflict == Skip("mode_b", ["PEER_CONFLICT"])
    result = strategy(ModeBStrategy).evaluate(ctx(session, OPTIONS, bear))
    assert isinstance(result, Proposal)
    assert result.construction == "put_spread"
    assert result.probability == pytest.approx(0.6)
    assert result.edge == pytest.approx(0.1)
    hot = {**OPTIONS, "positioning": {"pre_run_3d": 0.07}}
    assert strategy(ModeBStrategy).evaluate(ctx(session, hot, MOVE)) == Skip("mode_b", ["PRE_RUN"])
    reason = {**hot, "dossier": {"disclosure": 1.0}}  # рост с причиной — B без изменений
    with_reason = strategy(ModeBStrategy).evaluate(ctx(session, reason, MOVE))
    assert isinstance(with_reason, Proposal)
    assert with_reason.size_multiplier == 1.0
    warm = strategy(ModeBStrategy).evaluate(
        ctx(session, {**OPTIONS, "positioning": {"pre_run_3d": 0.04}}, MOVE)
    )
    assert isinstance(warm, Proposal)
    assert (warm.construction, warm.size_multiplier) == ("stock_collar", 0.5)
    dip = strategy(ModeBStrategy).evaluate(
        ctx(session, {**OPTIONS, "positioning": {"pre_run_3d": -0.05}}, MOVE)
    )
    assert isinstance(dip, Proposal)
    assert dip.size_multiplier == 1.2


def test_mode_b_informant_report_is_a_reason(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    edge = CONFIG.universe.peer_edges[0]  # «кто кому сигналит» из universe.yaml
    hot = {**OPTIONS, "positioning": {"pre_run_3d": 0.07}}
    before = strategy(ModeBStrategy).evaluate(ctx(session, hot, MOVE, edge.to_ticker))
    assert before == Skip("mode_b", ["PRE_RUN"])
    save_reported_earnings(
        session,
        [
            ReportedEarnings(
                ticker=edge.from_ticker,
                report_date=date(2026, 10, 15),  # за 4 дня до решения — в окне 14 дней
                report_time="AMC",
                fiscal_period_end=date(2026, 9, 30),
            )
        ],
    )
    after = strategy(ModeBStrategy).evaluate(ctx(session, hot, MOVE, edge.to_ticker))
    assert isinstance(after, Proposal)  # рост с причиной — отчёт информатора
