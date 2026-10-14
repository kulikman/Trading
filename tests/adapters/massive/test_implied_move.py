import math
from datetime import UTC, date, datetime
from typing import Any

import pytest

from adapters.errors import DataError
from adapters.massive.implied_move import ImpliedMove, implied_move
from adapters.massive.models import OptionSnapshot
from core.config.sources import MassiveSettings
from core.domain.types import ReportTime
from tests.adapters.massive.conftest import FakeMassive, fixture, make_client

LOOKAHEAD = 14
MAX_IV = 5.0
AS_OF = datetime(2026, 10, 13, 19, 0, tzinfo=UTC)  # 15:00 ET
GS_EXPIRY_CLOSE = datetime(2026, 10, 16, 20, 0, tzinfo=UTC)  # 16:00 ET


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


def run(
    rows: list[dict[str, Any]],
    report_date: date = date(2026, 10, 13),
    report_time: ReportTime = "BMO",
    as_of: datetime = AS_OF,
) -> ImpliedMove:
    return implied_move(
        StaticChain(rows),
        "GS",
        report_date,
        report_time,
        as_of=as_of,
        lookahead_days=LOOKAHEAD,
        max_plausible_iv=MAX_IV,
    )


def without_quotes() -> list[dict[str, Any]]:
    rows = chain_rows()
    for row in rows:
        row.pop("last_quote")
    return rows


# --- по котировкам (тариф с котировками опционов) ---


def test_straddle_from_quotes_via_massive_client(settings: MassiveSettings) -> None:
    fake = FakeMassive({"/v3/snapshot/options/GS": lambda _: fixture("option_chain_gs")})
    result = implied_move(
        make_client(settings, fake),
        "GS",
        date(2026, 10, 13),
        "BMO",
        as_of=AS_OF,
        lookahead_days=settings.implied_move.expiration_lookahead_days,
        max_plausible_iv=settings.implied_move.max_plausible_iv,
    )
    assert (result.expiration, result.strike, result.underlying_price) == (
        date(2026, 10, 16),
        900,
        897.0,
    )
    assert result.method == "straddle_mid"
    assert result.straddle == pytest.approx(43.0)
    assert result.move == pytest.approx(43.0 / 897.0)
    params = fake.requests[0].url.params
    assert params["expiration_date.gte"] == "2026-10-13"
    assert params["expiration_date.lte"] == "2026-10-27"


def test_amc_friday_report_uses_next_week_expiration() -> None:
    result = run(chain_rows(), date(2026, 10, 16), "AMC")
    assert (result.reaction_day, result.expiration) == (date(2026, 10, 19), date(2026, 10, 23))
    assert result.straddle == pytest.approx(26.6 + 29.0)


def test_midpoint_missing_falls_back_to_bid_ask_average() -> None:
    rows = chain_rows()
    for row in rows:
        row["last_quote"].pop("midpoint")
    assert run(rows).straddle == pytest.approx(43.0)


# --- по IV (Options Starter: котировок нет) ---


def test_iv_approximation_when_plan_has_no_quotes() -> None:
    result = run(without_quotes())
    sigma = (0.60 + 0.62) / 2  # IV колла и пута на страйке 900
    years = (GS_EXPIRY_CLOSE - AS_OF).total_seconds() / (365 * 24 * 3600)
    expected = math.sqrt(2 / math.pi) * 897.0 * sigma * math.sqrt(years)
    assert result.method == "iv_approx"
    assert result.strike == 900
    assert result.straddle == pytest.approx(expected)
    assert result.move == pytest.approx(expected / 897.0)


def test_unusable_quote_falls_back_to_iv() -> None:
    rows = chain_rows()
    for row in rows:
        row["last_quote"]["bid"] = 0
    assert run(rows).method == "iv_approx"


def _no_quotes_and(change: str) -> list[dict[str, Any]]:
    rows = without_quotes()
    for row in rows:
        if change == "no-iv":
            row.pop("implied_volatility")
        elif change == "percent-iv":
            row["implied_volatility"] *= 100
    return rows


# --- нехватка данных: DataError, а не догадка ---


def _without(key: str) -> list[dict[str, Any]]:
    rows = chain_rows()
    for row in rows:
        row.pop(key)
    return rows


@pytest.mark.parametrize(
    ("rows", "as_of", "message"),
    [
        ([], AS_OF, "no option expirations"),
        (_without("underlying_asset"), AS_OF, "no underlying price"),
        (
            [r for r in chain_rows() if r["details"]["contract_type"] == "call"],
            AS_OF,
            "both a call and a put",
        ),
        (_no_quotes_and("no-iv"), AS_OF, "neither usable quotes nor IV"),
        (_no_quotes_and("percent-iv"), AS_OF, "implausible IV"),
        (without_quotes(), GS_EXPIRY_CLOSE, "already closed"),
    ],
    ids=["empty", "no-underlying", "calls-only", "no-quotes-no-iv", "percent-iv", "expired"],
)
def test_missing_data_is_data_error_not_a_guess(
    rows: list[dict[str, Any]], as_of: datetime, message: str
) -> None:
    with pytest.raises(DataError, match=message) as exc_info:
        run(rows, as_of=as_of)
    assert exc_info.value.source == "massive"


def test_expiration_on_a_holiday_is_data_error() -> None:
    rows = without_quotes()
    for row in rows:
        row["details"]["expiration_date"] = "2026-11-26"  # Thanksgiving
    with pytest.raises(DataError, match="not a trading day"):
        run(rows, date(2026, 11, 24), "BMO", datetime(2026, 11, 23, 19, 0, tzinfo=UTC))


def test_naive_as_of_rejected() -> None:
    with pytest.raises(ValueError, match="naive datetime"):
        run(chain_rows(), as_of=datetime(2026, 10, 13, 15, 0))  # noqa: DTZ001
