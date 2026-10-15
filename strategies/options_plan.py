"""План Real-сделки опционной конструкции по живой цепочке (E10-2b): контракты и лимиты.

Решение стрэддла и кондора — T−1 15:10 ET; цепочка Massive (Options Starter) даёт цену последней
сделки каждого контракта с задержкой 15 минут, котировок нет. Берутся только контракты экспирации
конструкции (ближайшая пятница не раньше реакции) со сделкой в день решения. Лимит ноги —
последняя сделка ± половина спреда по допущению CostModel (покупка дороже, продажа дешевле).
Риск единицы: стрэддл — уплаченная премия, кондор — ширина крыла − премия, плюс комиссия входа.
Вход — до закрытия дня решения (16:00 ET, как «по закрытию» в бэктесте). Стоп и цель конструкции —
правилом в карточке (по премии); выходы ведёт человек (E10-3).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time

from adapters.massive.models import OptionSnapshot
from backtest.signals import condor_strikes
from backtest.simulate import CONTRACT_MULTIPLIER
from core.config.thresholds import IronCondor, Straddle
from core.domain.broker import OptionRight, OptionSpec, Order, Side
from core.domain.trading import TradePlan
from core.session_guard import to_et
from execution.costs import CostLeg, CostModel

ENTRY_DEADLINE = time(16, 0)  # вход по закрытию дня решения
STRIKE_BAND = 0.30  # страйки ± 30% от цены — с запасом для крыльев кондора (2 implied move)


@dataclass(frozen=True)
class Contract:
    right: OptionRight
    strike: float
    expiration: date
    close: float


def traded_contracts(rows: Sequence[OptionSnapshot], expiration: date, day: date) -> list[Contract]:
    """Контракты экспирации конструкции со сделкой в день решения."""
    out = []
    for row in rows:
        session = row.day
        if row.details.expiration_date != expiration or session is None:
            continue
        if session.close is None or session.close <= 0 or session.last_updated is None:
            continue
        traded = to_et(datetime.fromtimestamp(session.last_updated / 1e9, tz=UTC)).date()
        if traded == day:
            right: OptionRight = "call" if row.details.contract_type == "call" else "put"
            out.append(Contract(right, row.details.strike_price, expiration, session.close))
    return out


def straddle_plan(
    ticker: str, contracts: Sequence[Contract], spot: float, rules: Straddle, costs: CostModel
) -> TradePlan | None:
    """Покупка колла и пута страйка, ближайшего к цене, где торговались обе ноги."""
    pair = _atm(contracts, spot)
    if pair is None:
        return None
    orders = tuple(_order(ticker, c, "buy", costs, n) for n, c in enumerate(pair))
    premium = sum(o.limit_price or 0.0 for o in orders)
    return TradePlan(
        orders=orders,
        unit_risk=premium * CONTRACT_MULTIPLIER + _commission(orders, costs),
        stop_rule=(
            f"стоп −{rules.stop_premium_loss:.0%} премии, цель +{rules.target_premium_gain:.0%}, "
            "выход до 11:00 ET дня реакции"
        ),
        entry_until_et=ENTRY_DEADLINE,
    )


def condor_plan(
    ticker: str,
    contracts: Sequence[Contract],
    spot: float,
    implied_move: float,
    rules: IronCondor,
    costs: CostModel,
) -> TradePlan | None:
    """Продажа колла и пута на short_implied_moves, покупка крыльев на wing_implied_moves."""
    calls = {c.strike: c for c in contracts if c.right == "call"}
    puts = {c.strike: c for c in contracts if c.right == "put"}
    strikes = condor_strikes(
        sorted(calls),
        sorted(puts),
        spot,
        implied_move,
        rules.short_implied_moves,
        rules.wing_implied_moves,
    )
    if strikes is None:
        return None
    legs: list[tuple[Contract, Side]] = [
        (calls[strikes.short_call], "sell"),
        (puts[strikes.short_put], "sell"),
        (calls[strikes.long_call], "buy"),
        (puts[strikes.long_put], "buy"),
    ]
    orders = tuple(_order(ticker, c, side, costs, n) for n, (c, side) in enumerate(legs))
    signed = [(o.limit_price or 0.0) * (1 if o.side == "sell" else -1) for o in orders]
    credit = sum(signed)
    width = max(strikes.long_call - strikes.short_call, strikes.short_put - strikes.long_put)
    if credit <= 0 or width <= credit:
        return None
    return TradePlan(
        orders=orders,
        unit_risk=(width - credit) * CONTRACT_MULTIPLIER + _commission(orders, costs),
        stop_rule=(
            f"премия {credit:.2f}: стоп — убыток {rules.stop_premium_multiple:g}× премии, "
            f"цель {rules.target_premium_share:.0%} премии, выход до 11:00 ET дня реакции"
        ),
        entry_until_et=ENTRY_DEADLINE,
    )


def _atm(contracts: Sequence[Contract], spot: float) -> tuple[Contract, Contract] | None:
    calls = {c.strike: c for c in contracts if c.right == "call"}
    puts = {c.strike: c for c in contracts if c.right == "put"}
    strikes = sorted(set(calls) & set(puts), key=lambda k: (abs(k - spot), k))
    return (calls[strikes[0]], puts[strikes[0]]) if strikes else None


def _order(ticker: str, contract: Contract, side: Side, costs: CostModel, n: int) -> Order:
    half = (
        costs.leg_cost(
            CostLeg("option", 1, CONTRACT_MULTIPLIER, contract.close), at_open=False
        ).spread
        / CONTRACT_MULTIPLIER
    )
    raw = contract.close + half if side == "buy" else contract.close - half
    limit = max(round(raw, 2), 0.01)
    code = "C" if contract.right == "call" else "P"
    return Order(
        client_order_id=f"plan-{n}",
        symbol=f"O:{ticker}{contract.expiration:%y%m%d}{code}{round(contract.strike * 1000):08d}",
        instrument="option",
        side=side,
        quantity=1,
        multiplier=CONTRACT_MULTIPLIER,
        order_type="limit",
        purpose="entry",
        limit_price=limit,
        option=OptionSpec(
            underlying=ticker,
            expiry=contract.expiration,
            strike=contract.strike,
            right=contract.right,
        ),
    )


def _commission(orders: Sequence[Order], costs: CostModel) -> float:
    return sum(
        costs.leg_cost(
            CostLeg("option", o.quantity, o.multiplier, o.limit_price or 0.0), at_open=False
        ).commission
        for o in orders
    )
