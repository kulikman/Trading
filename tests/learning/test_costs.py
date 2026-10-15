from datetime import UTC, datetime

from core.domain.broker import Fill, Order
from execution.costs import CostBreakdown, CostLeg
from learning.costs import NO_FILLS, RealExecution, compare_costs

AT = datetime(2026, 10, 13, 16, 0, tzinfo=UTC)


class HalfSpread:
    """Модель: полспреда $0,05 на акцию и комиссия $1 (в сравнение не входит)."""

    def leg_cost(self, leg: CostLeg, *, at_open: bool) -> CostBreakdown:
        return CostBreakdown(1.0, 0.05 * leg.quantity * leg.multiplier, 0.0, True)


def execution(
    n: int, *, side: str = "buy", kind: str = "stop", at: float = 100.0, price: float = 100.1
) -> RealExecution:
    """Стоп по 100, исполненный хуже на 0,10 — проскальзывание; лимит исполняется не хуже лимита."""
    prices = {"stop": {"stop_price": at}, "limit": {"limit_price": at}, "market": {}}[kind]
    order = Order.model_validate(
        {
            "client_order_id": f"c{n}",
            "symbol": "GS",
            "instrument": "stock",
            "side": side,
            "quantity": 10,
            "multiplier": 1,
            "purpose": "entry",
            "order_type": kind,
            **prices,
        }
    )
    fill = Fill(
        order_id=f"o{n}",
        client_order_id=f"c{n}",
        symbol="GS",
        instrument="stock",
        side=side,  # type: ignore[arg-type]
        quantity=10,
        multiplier=1,
        price=price,
        at=AT,
    )
    return RealExecution(order, fill)


def test_real_costs_twice_the_model_is_drift() -> None:
    fills = [execution(1), execution(2, side="sell", price=99.9)]
    result = compare_costs(fills, HalfSpread(), alert=0.2, min_fills=2)
    assert result.fills == 2
    assert round(result.real_cost, 6) == 2.0  # 0,10 хуже лимита × 10 акций × 2
    assert round(result.model_cost, 6) == 1.0
    assert result.divergence is not None
    assert round(result.divergence, 6) == 1.0
    assert result.drift
    assert result.text == "реальные выше модели на 100% (2 исполнения)"


def test_within_alert_is_not_drift() -> None:
    fills = [execution(1, price=100.055), execution(2, price=100.055)]
    result = compare_costs(fills, HalfSpread(), alert=0.2, min_fills=2)
    assert result.divergence is not None
    assert abs(result.divergence - 0.1) < 1e-6
    assert not result.drift


def test_too_few_fills_shows_divergence_without_conclusion() -> None:
    result = compare_costs([execution(1)], HalfSpread(), alert=0.2, min_fills=20)
    assert not result.drift
    assert result.text == "реальные выше модели на 100% (1 исполнение), вывод — от 20"


def test_market_orders_and_no_fills_give_no_data() -> None:
    result = compare_costs([execution(1, kind="market")], HalfSpread(), alert=0.2, min_fills=1)
    assert result.fills == 0
    assert result.divergence is None
    assert result.text == NO_FILLS


def test_limit_filled_better_means_costs_below_model() -> None:
    fills = [execution(n, kind="limit", price=99.95) for n in range(5)]
    result = compare_costs(fills, HalfSpread(), alert=0.2, min_fills=5)
    assert result.divergence is not None
    assert round(result.divergence, 6) == -2.0  # заплатили −$0,05 вместо +$0,05 на акцию
    assert result.drift
    assert result.text == "реальные ниже модели на 200% (5 исполнений)"
