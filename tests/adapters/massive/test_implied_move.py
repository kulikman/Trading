from datetime import date
from typing import Any

import pytest

from adapters.errors import DataError
from adapters.massive.implied_move import implied_move, reaction_day
from adapters.massive.models import OptionSnapshot
from core.config.sources import MassiveSettings
from tests.adapters.massive.conftest import FakeMassive, fixture, make_client

LOOKAHEAD = 14


def chain_rows() -> list[dict[str, Any]]:
    rows = fixture("option_chain_gs")["results"]
    assert isinstance(rows, list)
    return rows


class StaticChain:
    """Источник цепочки с фильтром по экспирации, как у API."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.snapshots = [OptionSnapshot.model_validate(row) for row in rows]

    def option_chain(
        self,
        underlying: str,
        *,
        expiration_gte: date | None = None,
        expiration_lte: date | None = None,
    ) -> list[OptionSnapshot]:
        return [
            s
            for s in self.snapshots
            if (expiration_gte is None or s.details.expiration_date >= expiration_gte)
            and (expiration_lte is None or s.details.expiration_date <= expiration_lte)
        ]


@pytest.mark.parametrize(
    ("report_date", "report_time", "expected"),
    [
        (date(2026, 10, 13), "BMO", date(2026, 10, 13)),
        (date(2026, 10, 13), "DURING", date(2026, 10, 13)),
        (date(2026, 10, 15), "AMC", date(2026, 10, 16)),
        (date(2026, 10, 16), "AMC", date(2026, 10, 19)),  # пятница → понедельник
        (date(2026, 11, 25), "AMC", date(2026, 11, 27)),  # через Thanksgiving
    ],
    ids=str,
)
def test_reaction_day(report_date: date, report_time: Any, expected: date) -> None:
    assert reaction_day(report_date, report_time) == expected


def test_implied_move_from_fixture_via_massive_client(settings: MassiveSettings) -> None:
    fake = FakeMassive({"/v3/snapshot/options/GS": lambda _: fixture("option_chain_gs")})
    result = implied_move(make_client(settings, fake), "GS", date(2026, 10, 13), "BMO", LOOKAHEAD)
    assert (result.expiration, result.strike, result.underlying_price) == (
        date(2026, 10, 16),
        900,
        897.0,
    )
    assert result.straddle == pytest.approx(43.0)
    assert result.move == pytest.approx(43.0 / 897.0)
    params = fake.requests[0].url.params
    assert params["expiration_date.gte"] == "2026-10-13"
    assert params["expiration_date.lte"] == "2026-10-27"


def test_amc_friday_report_uses_next_week_expiration() -> None:
    result = implied_move(StaticChain(chain_rows()), "GS", date(2026, 10, 16), "AMC", LOOKAHEAD)
    assert (result.reaction_day, result.expiration) == (date(2026, 10, 19), date(2026, 10, 23))
    assert result.straddle == pytest.approx(26.6 + 29.0)


def test_midpoint_missing_falls_back_to_bid_ask_average() -> None:
    rows = chain_rows()
    for row in rows:
        row["last_quote"].pop("midpoint")
    result = implied_move(StaticChain(rows), "GS", date(2026, 10, 13), "BMO", LOOKAHEAD)
    assert result.straddle == pytest.approx(43.0)


def _without(key: str) -> list[dict[str, Any]]:
    rows = chain_rows()
    for row in rows:
        row.pop(key)
    return rows


def _bad_bid() -> list[dict[str, Any]]:
    rows = chain_rows()
    for row in rows:
        row["last_quote"]["bid"] = 0
    return rows


@pytest.mark.parametrize(
    ("rows", "message"),
    [
        ([], "no option expirations"),
        (_without("last_quote"), "no quotes for ATM strike"),
        (_without("underlying_asset"), "no underlying price"),
        (
            [r for r in chain_rows() if r["details"]["contract_type"] == "call"],
            "both a call and a put",
        ),
        (_bad_bid(), "unusable quote"),
    ],
    ids=["empty", "no-quotes", "no-underlying", "calls-only", "zero-bid"],
)
def test_missing_data_is_data_error_not_a_guess(rows: list[dict[str, Any]], message: str) -> None:
    with pytest.raises(DataError, match=message) as exc_info:
        implied_move(StaticChain(rows), "GS", date(2026, 10, 13), "BMO", LOOKAHEAD)
    assert exc_info.value.source == "massive"
