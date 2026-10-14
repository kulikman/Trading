import pytest

from adapters.errors import DataError
from core.config import load_config
from core.config.broker import CostSettings
from execution.costs import BrokerCostModel, CostLeg, total_cost


@pytest.fixture
def settings() -> CostSettings:
    return load_config().broker.selected_costs


def model(settings: CostSettings, **overrides: object) -> BrokerCostModel:
    return BrokerCostModel(settings.model_copy(update=overrides))


def test_stock_with_quote(settings: CostSettings) -> None:
    leg = CostLeg("stock", quantity=300, multiplier=1, price=100.0, bid=99.98, ask=100.02)
    cost = model(settings).leg_cost(leg, at_open=False)
    assert cost.commission == pytest.approx(300 * 0.005)  # 1.50 > минимум 1.00
    assert cost.spread == pytest.approx(0.02 * 300)  # половина спреда 0.04
    assert (cost.slippage, cost.spread_assumed) == (0.0, False)
    assert cost.total == pytest.approx(1.5 + 6.0)


def test_stock_minimum_and_one_percent_cap(settings: CostSettings) -> None:
    small = CostLeg("stock", quantity=17, multiplier=1, price=897.0, bid=896.9, ask=897.1)
    assert model(settings).leg_cost(small, at_open=False).commission == pytest.approx(
        1.0
    )  # минимум
    cheap = CostLeg("stock", quantity=1000, multiplier=1, price=0.4, bid=0.39, ask=0.41)
    assert model(settings).leg_cost(cheap, at_open=False).commission == pytest.approx(
        0.01 * 1000 * 0.4
    )
    no_cap = model(settings, max_commission_stock_fraction=None).leg_cost(cheap, at_open=False)
    assert no_cap.commission == pytest.approx(5.0)


def test_option_leg_and_open_slippage(settings: CostSettings) -> None:
    leg = CostLeg("option", quantity=2, multiplier=100, price=6.5, bid=6.3, ask=6.7)
    regular = model(settings).leg_cost(leg, at_open=False)
    at_open = model(settings).leg_cost(leg, at_open=True)
    assert regular.commission == pytest.approx(2 * 0.65)
    assert regular.spread == pytest.approx(0.2 * 200)
    assert at_open.slippage == pytest.approx(6.5 * settings.open_slippage * 200)
    assert at_open.total > regular.total


def test_option_minimum_per_order(settings: CostSettings) -> None:
    leg = CostLeg("option", quantity=1, multiplier=100, price=6.5, bid=6.3, ask=6.7)
    assert (
        model(settings, min_commission_per_option_order=1.0).leg_cost(leg, at_open=False).commission
        == 1.0
    )


def test_no_quote_without_assumption_is_data_error(settings: CostSettings) -> None:
    leg = CostLeg("option", quantity=1, multiplier=100, price=6.5)
    with pytest.raises(DataError, match="no option quote and no assumed spread"):
        model(settings).leg_cost(leg, at_open=False)


def test_no_quote_uses_configured_assumption_and_flags_it(settings: CostSettings) -> None:
    leg = CostLeg("option", quantity=1, multiplier=100, price=6.0)
    cost = model(settings, assumed_spread_option=0.04).leg_cost(leg, at_open=True)
    assert cost.spread == pytest.approx(6.0 * 0.04 / 2 * 100)
    assert cost.slippage == pytest.approx(6.0 * settings.open_slippage * 100)  # от опорной цены
    assert cost.spread_assumed is True
    stock = model(settings, assumed_spread_stock=0.001).leg_cost(
        CostLeg("stock", quantity=10, multiplier=1, price=100.0), at_open=False
    )
    assert stock.spread == pytest.approx(0.05 * 10)


def test_total_cost_of_a_collar_entry(settings: CostSettings) -> None:
    legs = [
        CostLeg("stock", quantity=17, multiplier=1, price=897.0, bid=896.9, ask=897.1),
        CostLeg("option", quantity=1, multiplier=100, price=6.5, bid=6.3, ask=6.7),
        CostLeg("option", quantity=1, multiplier=100, price=5.8, bid=5.6, ask=6.0),
    ]
    total = total_cost(model(settings), legs, at_open=False)
    assert total.commission == pytest.approx(1.0 + 0.65 + 0.65)
    assert total.spread == pytest.approx(0.1 * 17 + 0.2 * 100 + 0.2 * 100)
    assert total.spread_assumed is False
    assert total_cost(model(settings), [], at_open=False).total == 0.0
