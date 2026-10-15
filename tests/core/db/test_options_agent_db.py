from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.errors import DataError
from adapters.fred.client import FredObservation
from adapters.massive.history import years_to_expiration
from adapters.massive.models import Bar, OptionContract, OptionSnapshot, TickerChange
from agents.options.agent import OptionsAgentPlugin
from core.config import load_config
from core.db import models as orm
from core.db.store import save_option_bars, save_reported_earnings, set_date_check, sync_universe
from core.domain.earnings import ReportedEarnings
from core.domain.options import OptionDailyBar
from core.domain.types import OptionType
from core.pricing.black_scholes import price
from core.registry.protocols import EventContext
from core.session_guard import ET, previous_trading_day

CONFIG = load_config()
SETTINGS = CONFIG.thresholds.agents.options
HISTORY = CONFIG.sources.massive.history
RUN_AT = datetime(2026, 10, 14, 19, 0, tzinfo=UTC)  # 15:00 ET, задача T−7
CLOSE_DAY = date(2026, 10, 13)
REPORT = date(2026, 10, 20)  # AMC → реакция 21.10
FRONT, BACK = date(2026, 10, 23), date(2026, 11, 20)
SPOT, RATE = 100.0, 0.04
STRIKES = [80 + 2.5 * i for i in range(17)]  # 80 … 120


def front_sigma(kind: OptionType, strike: float) -> float:
    """Ближняя: ATM 60%, путы ниже цены 66%, коллы выше — 56% → skew_25d = 0.10."""
    if strike == SPOT:
        return 0.60
    return 0.66 if kind == "put" and strike < SPOT else 0.56


def contract(kind: OptionType, strike: float, expiration: date) -> OptionContract:
    code = f"O:NFLX{expiration:%y%m%d}{kind[0].upper()}{int(strike * 1000):08d}"
    return OptionContract.model_validate(
        {
            "ticker": code,
            "underlying_ticker": "NFLX",
            "contract_type": kind,
            "exercise_style": "american",
            "expiration_date": expiration,
            "strike_price": strike,
            "shares_per_contract": 100,
        }
    )


def bar(day: date, close: float) -> Bar:
    start = datetime.combine(day, time(0), tzinfo=ET).timestamp() * 1000
    return Bar.model_validate({"o": close, "h": close, "l": close, "c": close, "v": 10, "t": start})


class Source:
    def __init__(self, untraded: frozenset[str] = frozenset()) -> None:
        self.contracts = {
            c.ticker: c
            for e in (FRONT, BACK)
            for k in STRIKES
            for c in (contract("call", k, e), contract("put", k, e))
        }
        self.untraded = untraded
        self.requests: list[str] = []

    def option_contracts(self, underlying: str, **kwargs: Any) -> list[OptionContract]:
        return list(self.contracts.values())

    def aggregates(
        self,
        ticker: str,
        multiplier: int,
        timespan: Any,
        start: date,
        end: date,
        *,
        adjusted: bool = True,
    ) -> list[Bar]:
        self.requests.append(ticker)
        if ticker == "NFLX":  # акция: 100 каждый торговый день
            out, day = [], end
            while day >= start:
                out.append(bar(day, SPOT))
                day = previous_trading_day(day)
            return list(reversed(out))
        if ticker in self.untraded:
            return []
        c = self.contracts[ticker]
        kind: OptionType = "call" if c.contract_type == "call" else "put"
        sigma = front_sigma(kind, c.strike_price) if c.expiration_date == FRONT else 0.40
        years = years_to_expiration(CLOSE_DAY, c.expiration_date)
        return [bar(CLOSE_DAY, price(kind, SPOT, c.strike_price, years, RATE, sigma))]

    def ticker_changes(self, ticker: str) -> list[TickerChange]:
        return []

    def option_chain(self, underlying: str, **kwargs: Any) -> list[OptionSnapshot]:
        raise DataError("massive", "HTTP 403 NOT_AUTHORIZED")  # тариф без снимка — запасной путь


class Fred:
    def observations(
        self, series_id: str, start: date | None = None, end: date | None = None
    ) -> list[FredObservation]:
        assert series_id == "DGS3MO"
        assert start is not None
        assert end is not None
        return [
            FredObservation(date=start + timedelta(days=i), value=4.0)
            for i in range((end - start).days + 1)
        ]


def ctx(session: Session) -> EventContext:
    return EventContext(
        event_id=1,
        ticker="NFLX",
        report_date=REPORT,
        report_time="AMC",
        stage="T-7",
        as_of=RUN_AT,
        session=session,
    )


def trading_days_before(day: date, count: int) -> date:
    for _ in range(count):
        day = previous_trading_day(day)
    return day


def archive_past(session: Session, reports: list[tuple[date, date, float]]) -> None:
    """Прошлые отчёты AMC: (дата отчёта, день реакции, ATM IV за 6 торговых дней до реакции)."""
    save_reported_earnings(
        session,
        [
            ReportedEarnings(
                ticker="NFLX",
                report_date=d,
                report_time="AMC",
                fiscal_period_end=d - timedelta(days=20),
                eps_surprise_pct=1.0,
            )
            for d, _, _ in reports
        ],
    )
    bars = []
    for _, reaction, sigma in reports:
        day = trading_days_before(reaction, 6)  # 13.10 → 21.10: тоже 6 торговых дней
        expiration = reaction + timedelta(days=(4 - reaction.weekday()) % 7)  # пятница реакции
        years = years_to_expiration(day, expiration)
        for kind in ("call", "put"):
            c = contract(kind, SPOT, expiration)
            close = price(kind, SPOT, SPOT, years, RATE, sigma)
            bars.append(
                OptionDailyBar(
                    option_ticker=c.ticker,
                    day=day,
                    underlying="NFLX",
                    expiration=expiration,
                    strike=SPOT,
                    option_type=kind,
                    open=close,
                    high=close,
                    low=close,
                    close=close,
                    volume=5,
                )
            )
    save_option_bars(session, bars)


PAST = [
    (date(2025, 10, 21), date(2025, 10, 22), 0.40),
    (date(2026, 1, 20), date(2026, 1, 21), 0.50),
    (date(2026, 4, 16), date(2026, 4, 17), 0.70),
    (date(2026, 7, 16), date(2026, 7, 17), 0.80),
]


def test_features_by_hand_and_bars_archived(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    archive_past(session, PAST)
    source = Source()
    features = OptionsAgentPlugin(source, Fred(), HISTORY, SETTINGS).run(ctx(session))
    years = years_to_expiration(CLOSE_DAY, FRONT)
    straddle = price("call", SPOT, SPOT, years, RATE, 0.60) + price(
        "put", SPOT, SPOT, years, RATE, 0.60
    )
    assert features.implied_move == pytest.approx(straddle / SPOT)
    assert features.atm_iv == pytest.approx(0.60, abs=1e-4)
    assert features.skew_25d == pytest.approx(0.66 - 0.56, abs=1e-4)
    assert features.term_slope == pytest.approx(0.60 - 0.40, abs=1e-4)
    # прошлые IV на той же стадии: 0.40, 0.50 ниже текущей 0.60; 0.70, 0.80 выше
    assert (features.iv_rank, features.iv_rank_reports) == (0.5, 4)
    # 25Δ: колл ~107.6 → 107.5, пут ~94.1 → 95; дальняя — 20.11 (≥ 23.10 + 28 дней)
    assert [t for t in source.requests if t != "NFLX"] == [
        "O:NFLX261023C00100000",
        "O:NFLX261023P00100000",
        "O:NFLX261023P00095000",
        "O:NFLX261023C00107500",
        "O:NFLX261120C00100000",
        "O:NFLX261120P00100000",
    ]
    archived = session.scalars(
        select(orm.OptionDailyBar.option_ticker).where(orm.OptionDailyBar.day == CLOSE_DAY)
    ).all()
    assert len(archived) == 6  # скачанные цены — в архив


def test_iv_rank_needs_enough_reports_and_skips_mismatch(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    archive_past(session, PAST)
    set_date_check(session, "NFLX", PAST[0][0], None, "mismatch")
    features = OptionsAgentPlugin(Source(), Fred(), HISTORY, SETTINGS).run(ctx(session))
    assert (features.iv_rank, features.iv_rank_reports) == (None, 3)  # меньше 4 — не считается


def test_untraded_atm_moves_to_next_strike(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    untraded = frozenset({"O:NFLX261023C00100000"})
    features = OptionsAgentPlugin(Source(untraded), Fred(), HISTORY, SETTINGS).run(ctx(session))
    # следующая пара — 97,5 (при равном расстоянии с 102,5 — меньший страйк): колл 56%, пут 66%
    assert features.atm_iv == pytest.approx((0.56 + 0.66) / 2, abs=1e-3)
    assert features.iv_rank is None


def test_no_traded_pair_is_data_error(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    calls = frozenset(contract("call", k, FRONT).ticker for k in STRIKES)
    with pytest.raises(DataError, match="no ATM pair traded"):
        OptionsAgentPlugin(Source(calls), Fred(), HISTORY, SETTINGS).run(ctx(session))


def test_needs_archive_session() -> None:
    agent = OptionsAgentPlugin(Source(), Fred(), HISTORY, SETTINGS)
    no_session = EventContext(
        event_id=1, ticker="NFLX", report_date=REPORT, report_time="AMC", stage="T-7", as_of=RUN_AT
    )
    with pytest.raises(DataError, match="archive session"):
        agent.run(no_session)


TODAY = date(2026, 10, 14)


def snapshot(
    kind: OptionType, strike: float, expiration: date, close: float | None, iv: float, delta: float
) -> OptionSnapshot:
    return OptionSnapshot.model_validate(
        {
            "details": {
                "contract_type": kind,
                "exercise_style": "american",
                "expiration_date": expiration,
                "shares_per_contract": 100,
                "strike_price": strike,
                "ticker": contract(kind, strike, expiration).ticker,
            },
            "day": {"close": close, "volume": 10},
            "greeks": {"delta": delta},
            "implied_volatility": iv,
            "open_interest": 100,
        }
    )


CHAIN = [
    snapshot("call", 100, FRONT, 4.0, 0.58, 0.55),
    snapshot("put", 100, FRONT, 3.0, 0.62, -0.45),
    snapshot("call", 101, FRONT, None, 0.57, 0.50),  # без сделки — не ATM, хотя ближе к цене
    snapshot("put", 101, FRONT, 3.5, 0.61, -0.50),
    snapshot("put", 95, FRONT, 1.0, 0.66, -0.24),
    snapshot("put", 90, FRONT, 0.4, 0.70, -0.10),
    snapshot("call", 107.5, FRONT, 0.9, 0.56, 0.26),
    snapshot("call", 115, FRONT, 0.2, 0.55, 0.08),
    snapshot("call", 100, BACK, 6.0, 0.41, 0.55),
    snapshot("put", 100, BACK, 5.0, 0.39, -0.45),
]


class ChainSource(Source):
    def __init__(self, chain: list[OptionSnapshot]) -> None:
        super().__init__()
        self.chain = chain

    def option_chain(self, underlying: str, **kwargs: Any) -> list[OptionSnapshot]:
        assert kwargs["expiration_gte"] == date(2026, 10, 21)  # не раньше дня реакции
        return self.chain

    def aggregates(
        self,
        ticker: str,
        multiplier: int,
        timespan: Any,
        start: date,
        end: date,
        *,
        adjusted: bool = True,
    ) -> list[Bar]:
        if timespan != "minute":
            return super().aggregates(ticker, multiplier, timespan, start, end, adjusted=adjusted)
        assert (ticker, start, end) == ("NFLX", TODAY, TODAY)
        minute = datetime.combine(TODAY, time(14, 44), tzinfo=ET).timestamp() * 1000
        late = datetime.combine(TODAY, time(15, 30), tzinfo=ET).timestamp() * 1000
        return [
            Bar.model_validate({"o": 1, "h": 1, "l": 1, "c": 101.0, "v": 1, "t": minute}),
            Bar.model_validate({"o": 1, "h": 1, "l": 1, "c": 999.0, "v": 1, "t": late}),
        ]


def test_chain_features_by_hand(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    source = ChainSource(CHAIN)
    features = OptionsAgentPlugin(source, Fred(), HISTORY, SETTINGS).run(ctx(session))
    assert features.implied_move == pytest.approx((4.0 + 3.0) / 101.0)  # цена — минута 14:44
    assert features.atm_iv == pytest.approx(0.60)
    assert features.skew_25d == pytest.approx(0.66 - 0.56)  # дельты −0,24 и 0,26
    assert features.term_slope == pytest.approx(0.60 - 0.40)
    assert [t for t in source.requests if t != "NFLX"] == []  # свечи контрактов не нужны
    assert session.scalars(select(orm.OptionDailyBar)).all() == []


def test_chain_without_atm_pair_falls_back_to_closes(session: Session) -> None:
    sync_universe(session, CONFIG.universe)
    calls_only = [s for s in CHAIN if s.details.contract_type == "call"]
    source = ChainSource(calls_only)
    features = OptionsAgentPlugin(source, Fred(), HISTORY, SETTINGS).run(ctx(session))
    assert features.atm_iv == pytest.approx(0.60, abs=1e-4)  # IV по закрытиям накануне
    assert "O:NFLX261023C00100000" in source.requests
