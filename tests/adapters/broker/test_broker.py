import ast
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest

from adapters.broker.base import (
    BrokerAdapter,
    MarketOrderTooEarlyError,
    OutsideSessionError,
    check_order_allowed,
)
from adapters.broker.factory import create_broker, create_cost_model
from adapters.broker.manual import (
    ManualBroker,
    OrderNotPendingError,
    UnknownOrderError,
    instruction_line,
)
from adapters.broker.stubs import FreedomBroker, IbBroker
from core.config import load_config
from core.config.broker import BrokerConfig
from core.domain.broker import Order, OrderId, Quote
from core.session_guard import ET
from execution.costs import BrokerCostModel

FIVE = 5
OPEN = datetime(2026, 10, 13, 9, 30, tzinfo=ET)  # вторник
MIDDAY = datetime(2026, 10, 13, 12, 0, tzinfo=ET)
REPO = Path(__file__).resolve().parents[3]


def order(**overrides: Any) -> Order:
    fields: dict[str, Any] = {
        "client_order_id": "card-1-leg-1",
        "symbol": "GS",
        "instrument": "stock",
        "side": "buy",
        "quantity": 17,
        "multiplier": 1,
        "order_type": "limit",
        "purpose": "entry",
        "limit_price": 897.0,
    }
    return Order(**(fields | overrides))


PUT_OPTION: dict[str, Any] = {
    "underlying": "GS",
    "expiry": date(2026, 10, 16),
    "strike": 850,
    "right": "put",
}
PUT: dict[str, Any] = {
    "symbol": "GS261016P00850000",
    "instrument": "option",
    "quantity": 1,
    "multiplier": 100,
    "limit_price": 6.5,
    "option": PUT_OPTION,
}


def quote_source(symbol: str) -> Quote:
    return Quote(symbol=symbol, bid=896.9, ask=897.1, at=MIDDAY)


def broker(now: datetime = MIDDAY) -> ManualBroker:
    return ManualBroker(
        quote_source=quote_source, no_market_orders_first_minutes=FIVE, clock=lambda: now
    )


# --- можно ли ставить ордер ---


@pytest.mark.parametrize(
    ("now", "kind", "purpose", "error"),
    [
        (
            datetime(2026, 10, 13, 9, 29, tzinfo=ET),
            "limit",
            "entry",
            OutsideSessionError,
        ),  # пре-маркет
        (
            datetime(2026, 10, 13, 16, 0, tzinfo=ET),
            "limit",
            "exit",
            OutsideSessionError,
        ),  # после закрытия
        (
            datetime(2026, 10, 17, 12, 0, tzinfo=ET),
            "limit",
            "entry",
            OutsideSessionError,
        ),  # суббота
        (
            datetime(2026, 11, 26, 12, 0, tzinfo=ET),
            "limit",
            "entry",
            OutsideSessionError,
        ),  # Thanksgiving
        (
            datetime(2026, 11, 27, 13, 30, tzinfo=ET),
            "limit",
            "exit",
            OutsideSessionError,
        ),  # сокращённый день
        (datetime(2026, 10, 13, 9, 34, tzinfo=ET), "market", "exit", MarketOrderTooEarlyError),
        (datetime(2026, 10, 13, 9, 30, tzinfo=ET), "market", "stop", MarketOrderTooEarlyError),
    ],
    ids=[
        "pre-market",
        "after-close",
        "weekend",
        "holiday",
        "early-close",
        "market-0934",
        "market-0930-stop",
    ],
)
def test_order_rejected(now: datetime, kind: str, purpose: str, error: type[Exception]) -> None:
    extra = {"limit_price": None} if kind == "market" else {}
    with pytest.raises(error):
        check_order_allowed(order(order_type=kind, purpose=purpose, **extra), now, FIVE)


@pytest.mark.parametrize(
    ("now", "kind", "purpose"),
    [
        (OPEN, "market", "stop_gap"),  # стоп-гэп — единственное исключение в первые минуты
        (OPEN, "limit", "entry"),
        (datetime(2026, 10, 13, 9, 35, tzinfo=ET), "market", "exit"),
        (
            datetime(2026, 11, 2, 14, 30, tzinfo=UTC),
            "limit",
            "entry",
        ),  # 9:30 EST после смены времени
    ],
    ids=["stop-gap-at-open", "limit-at-open", "market-0935", "after-dst"],
)
def test_order_allowed(now: datetime, kind: str, purpose: str) -> None:
    extra = {"limit_price": None} if kind == "market" else {}
    check_order_allowed(order(order_type=kind, purpose=purpose, **extra), now, FIVE)


def test_place_outside_session_raises_and_records_nothing() -> None:
    manual = broker(datetime(2026, 10, 13, 18, 0, tzinfo=ET))
    with pytest.raises(OutsideSessionError):
        manual.place(order())
    assert manual.fills(datetime(2026, 1, 1, tzinfo=UTC)) == []
    with pytest.raises(UnknownOrderError):
        manual.instruction(OrderId("manual-card-1-leg-1"))


# --- ManualBroker ---


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, "Купить  GS  17 шт.  лимит ≤ 897.00"),
        (PUT, "Купить  PUT 850 16.10  1 шт.  лимит ≤ 6.50"),
        (
            {
                **PUT,
                "side": "sell",
                "limit_price": 5.8,
                "option": {**PUT_OPTION, "strike": 960, "right": "call"},
            },
            "Продать  CALL 960 16.10  1 шт.  лимит ≥ 5.80",
        ),
        (
            {
                "side": "sell",
                "order_type": "stop",
                "purpose": "stop",
                "limit_price": None,
                "stop_price": 870,
            },
            "Продать  GS  17 шт.  стоп 870.00 (только основная сессия)",
        ),
        (
            {"side": "sell", "order_type": "market", "purpose": "stop_gap", "limit_price": None},
            "Продать  GS  17 шт.  по рынку",
        ),
    ],
    ids=["stock-limit", "put-buy", "call-sell", "stop", "market"],
)
def test_instruction_lines_follow_card_template(overrides: dict[str, Any], expected: str) -> None:
    assert instruction_line(order(**overrides)) == expected


def test_place_is_idempotent_and_sends_nothing() -> None:
    manual = broker()
    first = manual.place(order())
    assert manual.place(order()) == first  # повтор события — тот же ордер
    assert manual.instruction(first) == "Купить  GS  17 шт.  лимит ≤ 897.00"
    assert manual.positions() == []  # без «Исполнено» позиции нет


def test_confirm_fill_twice_returns_same_fill_and_builds_position() -> None:
    manual = broker()
    order_id = manual.place(order())
    fill = manual.confirm_fill(order_id, price=896.5, at=MIDDAY)
    assert manual.confirm_fill(order_id, price=999.0, at=MIDDAY) == fill
    assert manual.fills(MIDDAY) == [fill]
    assert manual.fills(datetime(2026, 10, 14, tzinfo=UTC)) == []
    [position] = manual.positions()
    assert (position.symbol, position.quantity, position.average_price) == ("GS", 17, 896.5)


def test_positions_average_price_and_partial_close() -> None:
    manual = broker()
    buy_1 = manual.place(order(client_order_id="b1", quantity=10, limit_price=100.0))
    buy_2 = manual.place(order(client_order_id="b2", quantity=10, limit_price=110.0))
    sell = manual.place(order(client_order_id="s1", side="sell", quantity=5, limit_price=120.0))
    manual.confirm_fill(buy_1, price=100.0, at=datetime(2026, 10, 13, 13, 40, tzinfo=UTC))
    manual.confirm_fill(buy_2, price=110.0, at=datetime(2026, 10, 13, 13, 50, tzinfo=UTC))
    manual.confirm_fill(sell, price=120.0, at=datetime(2026, 10, 13, 14, 0, tzinfo=UTC))
    [position] = manual.positions()
    assert position.quantity == 15
    assert position.average_price == pytest.approx(105.0)
    close = manual.place(order(client_order_id="s2", side="sell", quantity=15, limit_price=121.0))
    manual.confirm_fill(close, price=121.0, at=datetime(2026, 10, 13, 15, 0, tzinfo=UTC))
    assert manual.positions() == []


def test_cancel_blocks_fill_and_unknown_ids_raise() -> None:
    manual = broker()
    order_id = manual.place(order())
    manual.cancel(order_id)
    manual.cancel(order_id)  # повторная отмена — без ошибки
    with pytest.raises(OrderNotPendingError):
        manual.confirm_fill(order_id, price=1.0, at=MIDDAY)
    with pytest.raises(UnknownOrderError):
        manual.cancel(OrderId("manual-missing"))


def test_cancel_after_fill_keeps_fill() -> None:
    manual = broker()
    order_id = manual.place(order())
    fill = manual.confirm_fill(order_id, price=897.0, at=MIDDAY)
    manual.cancel(order_id)
    assert manual.confirm_fill(order_id, price=1.0, at=MIDDAY) == fill


def test_quote_comes_from_snapshot_source() -> None:
    assert broker().quote("GS").mid == pytest.approx(897.0)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"limit_price": None}, "limit order needs limit_price"),
        ({"order_type": "stop", "limit_price": None}, "stop order needs stop_price"),
        ({"order_type": "market"}, "market order takes no"),
        ({"instrument": "option", "multiplier": 100}, "option order needs option spec"),
        ({"multiplier": 100}, "stock order has multiplier 1"),
    ],
)
def test_invalid_orders(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        order(**overrides)


def test_crossed_quote_rejected() -> None:
    with pytest.raises(ValueError, match="ask below bid"):
        Quote(symbol="GS", bid=2, ask=1, at=MIDDAY)


# --- выбор брокера в конфиге ---


def place_with(adapter: BrokerAdapter) -> str:
    """Пример кода вне adapters/broker: знает только интерфейс."""
    return adapter.place(order())


def config_with(name: str) -> BrokerConfig:
    base = load_config().broker
    return BrokerConfig.model_validate(
        {"broker": name, "costs": {name: base.costs["manual"].model_dump()}}
    )


def test_switching_broker_is_config_only() -> None:
    manual = create_broker(
        config_with("manual"),
        quote_source=quote_source,
        no_market_orders_first_minutes=FIVE,
        clock=lambda: MIDDAY,
    )
    assert place_with(manual) == "manual-card-1-leg-1"
    for name, stub in (("ib", IbBroker), ("freedom", FreedomBroker)):
        adapter = create_broker(
            config_with(name),
            quote_source=quote_source,
            no_market_orders_first_minutes=FIVE,
            clock=lambda: MIDDAY,
        )
        assert isinstance(adapter, stub)
        with pytest.raises(NotImplementedError, match="phase 5"):
            place_with(adapter)
        assert_every_call_not_implemented(adapter)
    assert isinstance(create_cost_model(config_with("ib")), BrokerCostModel)


def assert_every_call_not_implemented(adapter: BrokerAdapter) -> None:
    with pytest.raises(NotImplementedError):
        adapter.quote("GS")
    with pytest.raises(NotImplementedError):
        adapter.cancel(OrderId("x"))
    with pytest.raises(NotImplementedError):
        adapter.positions()
    with pytest.raises(NotImplementedError):
        adapter.fills(MIDDAY)


def test_selected_broker_needs_a_cost_model() -> None:
    with pytest.raises(ValueError, match="no cost model for selected broker freedom"):
        BrokerConfig.model_validate({"broker": "freedom", "costs": {}})


def test_no_code_outside_adapters_broker_imports_a_concrete_broker() -> None:
    allowed = {"adapters.broker.base", "adapters.broker.factory"}
    offenders: list[str] = []
    for path in REPO.rglob("*.py"):
        relative = path.relative_to(REPO)
        if relative.parts[0] in {".venv", "tests"} or relative.parts[:2] == ("adapters", "broker"):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            offenders += [
                f"{relative}: {n}"
                for n in names
                if n.startswith("adapters.broker.") and n not in allowed
            ]
    assert offenders == []


def test_default_clock_is_timezone_aware() -> None:
    from adapters.broker.base import utc_now

    assert utc_now().tzinfo is UTC
