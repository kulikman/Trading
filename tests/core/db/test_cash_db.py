from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session

from execution.cash import real_capital, record_cash

AT = datetime(2026, 10, 15, tzinfo=UTC)


def test_real_capital_from_movements(session: Session) -> None:
    assert real_capital(session) is None  # движений нет — Real не подключён
    record_cash(session, "deposit", Decimal("10000"), "старт", AT)
    record_cash(session, "withdraw", Decimal("2500.50"), None, AT)
    assert real_capital(session) == pytest.approx(7499.5)


@pytest.mark.parametrize(
    ("kind", "amount"), [("bonus", "100"), ("deposit", "0"), ("withdraw", "-5")]
)
def test_bad_movement_rejected(session: Session, kind: str, amount: str) -> None:
    with pytest.raises(ValueError, match=r"deposit\|withdraw"):
        record_cash(session, kind, Decimal(amount), None, AT)
