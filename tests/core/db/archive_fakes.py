"""Фейковые источники архива для тестов T10 / T11: отчёты NFLX (AMC) в окне 2 лет."""

from datetime import date, datetime, time, timedelta
from typing import Any

from adapters.alphavantage.models import AvEarnings
from adapters.errors import DataError
from adapters.massive.models import Bar, OptionContract
from core.config import load_config
from core.session_guard import ET

TODAY = date(2026, 10, 14)
CONFIG = load_config()
HISTORY = CONFIG.sources.massive.history

# Отчёты NFLX (AMC): два с ценами опционов, один без контрактов, один вне окна доступа (2 года).
TRADED = {
    date(2025, 10, 21): (date(2025, 10, 24), 100.0),
    date(2026, 1, 20): (date(2026, 1, 23), 90.0),
}
NO_CONTRACTS = date(2026, 7, 16)
TOO_OLD = date(2024, 7, 18)
# Конец фискального квартала каждого отчёта (Alpha Vantage даёт конец месяца).
FISCAL_END = {
    date(2025, 10, 21): date(2025, 9, 30),
    date(2026, 1, 20): date(2025, 12, 31),
    NO_CONTRACTS: date(2026, 6, 30),
    TOO_OLD: date(2024, 6, 30),
}
# Закрытия акции: накануне (= день отчёта, AMC) и в день реакции (следующий торговый день).
CLOSES = {
    TOO_OLD: 600.0,
    date(2024, 7, 19): 630.0,  # +5%: старше окна опционов, но в окне цен акций (5 лет)
    date(2025, 10, 21): 100.0,
    date(2025, 10, 22): 110.0,  # +10% при ожидании 7%
    date(2026, 1, 20): 90.0,
    date(2026, 1, 21): 85.5,  # −5% при ожидании 7,8%
    NO_CONTRACTS: 80.0,
    date(2026, 7, 17): 84.0,  # +5%, implied move нет
}


def bar(day: date, close: float) -> Bar:
    start = datetime.combine(day, time(0), tzinfo=ET).timestamp() * 1000
    return Bar.model_validate({"o": close, "h": close, "l": close, "c": close, "v": 50, "t": start})


def contract(kind: str, strike: float, expiration: date) -> OptionContract:
    letter = "C" if kind == "call" else "P"
    return OptionContract.model_validate(
        {
            "ticker": f"O:NFLX{expiration:%y%m%d}{letter}{int(strike * 1000):08d}",
            "underlying_ticker": "NFLX",
            "contract_type": kind,
            "exercise_style": "american",
            "expiration_date": expiration.isoformat(),
            "strike_price": strike,
            "shares_per_contract": 100,
        }
    )


class Options:
    """ATM-пара на каждый отчёт из TRADED; пре-день = день отчёта (AMC)."""

    def __init__(self) -> None:
        self.contract_calls = 0
        self.aggregate_calls: list[str] = []
        self.contracts: list[OptionContract] = []
        self.bars: dict[str, list[Bar]] = {}
        for report, (expiration, spot) in TRADED.items():
            for kind, price in (("call", 4.0), ("put", 3.0)):
                item = contract(kind, spot, expiration)
                self.contracts.append(item)
                self.bars[item.ticker] = [bar(report - timedelta(days=1), 1.0), bar(report, price)]

    def option_contracts(self, underlying: str, **kwargs: Any) -> list[OptionContract]:
        self.contract_calls += 1
        low, high = kwargs["expiration_gte"], kwargs["expiration_lte"]
        return [c for c in self.contracts if low <= c.expiration_date <= high]

    def aggregates(self, ticker: str, *args: Any, **kwargs: Any) -> list[Bar]:
        self.aggregate_calls.append(ticker)
        return self.bars.get(ticker, [])


class Stocks:
    def __init__(self) -> None:
        self.calls: list[tuple[date, date, bool]] = []

    def aggregates(
        self,
        ticker: str,
        multiplier: int,
        timespan: str,
        start: date,
        end: date,
        *,
        adjusted: bool = True,
    ) -> list[Bar]:
        self.calls.append((start, end, adjusted))
        return [bar(d, c) for d, c in CLOSES.items()]

    def ticker_changes(self, ticker: str) -> list[Any]:
        return []


class Earnings:
    def __init__(self, error: DataError | None = None) -> None:
        self.error = error
        self.calls = 0

    def earnings(self, symbol: str) -> AvEarnings:
        self.calls += 1
        if self.error is not None:
            raise self.error
        reports = [*TRADED, NO_CONTRACTS, TOO_OLD]
        return AvEarnings.model_validate(
            {
                "symbol": symbol,
                "quarterlyEarnings": [
                    {
                        "fiscalDateEnding": FISCAL_END[d].isoformat(),
                        "reportedDate": d.isoformat(),
                        "reportTime": "post-market",
                        "reportedEPS": "1.1",
                        "estimatedEPS": "1.0",
                        "surprisePercentage": "10",
                    }
                    for d in reports
                ],
            }
        )
