from datetime import date, datetime, time

import pytest

from adapters.broker.factory import create_cost_model
from adapters.massive.models import OptionSnapshot
from core.config import load_config
from core.session_guard import ET
from strategies.options_plan import condor_plan, straddle_plan, traded_contracts

CONFIG = load_config()
COSTS = create_cost_model(CONFIG.broker)
DAY = date(2026, 10, 19)  # T−1, решение 15:10 ET
EXPIRY = date(2026, 10, 23)
RULES = CONFIG.thresholds.constructions


def row(
    right: str, strike: float, close: float, traded_on: date = DAY, expiry: date = EXPIRY
) -> OptionSnapshot:
    stamp = int(datetime.combine(traded_on, time(14, 50), tzinfo=ET).timestamp() * 1e9)
    return OptionSnapshot.model_validate(
        {
            "details": {
                "contract_type": right,
                "exercise_style": "american",
                "expiration_date": expiry,
                "shares_per_contract": 100,
                "strike_price": strike,
                "ticker": f"O:NFLX{right}{strike}",
            },
            "day": {"close": close, "volume": 10, "last_updated": stamp},
            "implied_volatility": 0.5,
        }
    )


def test_traded_contracts_filter_expiry_and_day() -> None:
    rows = [
        row("call", 100, 5.0),
        row("call", 105, 3.0, traded_on=date(2026, 10, 16)),  # сделка в прошлую сессию
        row("put", 100, 4.0, expiry=date(2026, 10, 30)),  # другая экспирация
    ]
    assert [(c.right, c.strike) for c in traded_contracts(rows, EXPIRY, DAY)] == [("call", 100)]


def test_straddle_plan_buys_atm_pair_with_half_spread() -> None:
    contracts = traded_contracts(
        [row("call", 100, 5.0), row("put", 100, 4.0), row("call", 105, 3.0)], EXPIRY, DAY
    )
    plan = straddle_plan("NFLX", contracts, 101.0, RULES.straddle, COSTS)
    assert plan is not None
    call, put = plan.orders
    # спред 3% → половина 1,5%: 5,00 → 5,075 → 5,08; 4,00 → 4,06
    assert (call.side, call.limit_price, put.side, put.limit_price) == ("buy", 5.08, "buy", 4.06)
    assert call.option is not None
    assert (call.option.right, call.option.strike, call.option.expiry) == ("call", 100, EXPIRY)
    assert call.symbol == "O:NFLX261023C00100000"
    commission = 2 * CONFIG.broker.selected_costs.commission_per_contract  # $0,65 за контракт
    assert plan.unit_risk == pytest.approx((5.08 + 4.06) * 100 + commission)
    assert plan.entry_until_et == time(16, 0)


def test_condor_plan_strikes_credit_and_risk() -> None:
    rows = [
        row("call", 110, 2.0),
        row("call", 120, 0.5),
        row("put", 90, 2.0),
        row("put", 80, 0.5),
        row("call", 100, 5.0),
        row("put", 100, 5.0),
    ]
    plan = condor_plan(
        "NFLX", traded_contracts(rows, EXPIRY, DAY), 100.0, 0.10, RULES.iron_condor, COSTS
    )
    assert plan is not None
    sides = [
        (
            o.option.right if o.option else "",
            o.option.strike if o.option else 0,
            o.side,
            o.limit_price,
        )
        for o in plan.orders
    ]
    assert sides == [
        ("call", 110, "sell", 1.97),
        ("put", 90, "sell", 1.97),
        ("call", 120, "buy", 0.51),
        ("put", 80, "buy", 0.51),
    ]
    credit = 1.97 * 2 - 0.51 * 2  # 2,92
    commission = 4 * CONFIG.broker.selected_costs.commission_per_contract
    assert plan.unit_risk == pytest.approx((10 - credit) * 100 + commission)  # ширина 10


def test_no_plan_without_pair_or_credit() -> None:
    only_calls = traded_contracts([row("call", 100, 5.0)], EXPIRY, DAY)
    assert straddle_plan("NFLX", only_calls, 100.0, RULES.straddle, COSTS) is None
    no_credit = traded_contracts(
        [row("call", 110, 0.01), row("call", 120, 0.5), row("put", 90, 0.01), row("put", 80, 0.5)],
        EXPIRY,
        DAY,
    )
    assert condor_plan("NFLX", no_credit, 100.0, 0.10, RULES.iron_condor, COSTS) is None
