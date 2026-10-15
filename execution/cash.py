"""Деньги счёта Real (T17, DASHBOARD §3): пополнения и выводы; Paper — капитал из thresholds.yaml.

`make cash ARGS="deposit 10000 первое пополнение"` / `ARGS="withdraw 2000"`. На сервере —
`ssh brain-hetzner 'docker exec trading-api python -m execution.cash deposit 10000'`.
"""

import logging
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.db import models as orm
from core.db.session import create_db_engine

logger = logging.getLogger(__name__)

USAGE = "использование: python -m execution.cash deposit|withdraw СУММА [комментарий]"


def real_capital(session: Session) -> float | None:
    """Капитал Real: сумма пополнений минус выводы; движений нет — счёт не подключён (None)."""
    total = session.scalar(
        select(func.sum(orm.CashMovement.amount)).where(orm.CashMovement.account == "real")
    )
    return None if total is None else float(total)


def real_balance(session: Session) -> float | None:
    """Счёт Real: пополнения − выводы + итог закрытых Real-сделок; движений нет — None."""
    capital = real_capital(session)
    if capital is None:
        return None
    pnl = session.scalar(
        select(func.sum(orm.TradeCard.pnl_total)).where(
            orm.TradeCard.paper.is_(False), orm.TradeCard.state.in_(("CLOSED", "STOPPED"))
        )
    )
    return capital + float(pnl or 0)


def reserved_cash(session: Session) -> float:
    """Деньги под открытыми и ждущими Real-позициями (cash_usd карточек)."""
    total = session.scalar(
        select(func.sum(orm.TradeCard.cash_usd)).where(
            orm.TradeCard.paper.is_(False),
            orm.TradeCard.state.in_(("PLANNED", "ARMED", "OPEN", "C_MODE", "CLOSING")),
        )
    )
    return float(total or 0)


def record_cash(
    session: Session, kind: str, amount: Decimal, note: str | None, at: datetime
) -> orm.CashMovement:
    """Записать пополнение (+) или вывод (−) счёта Real."""
    if kind not in ("deposit", "withdraw") or amount <= 0:
        raise ValueError(USAGE)
    row = orm.CashMovement(
        account="real", at=at, amount=amount if kind == "deposit" else -amount, note=note
    )
    session.add(row)
    session.flush()
    return row


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        kind, amount = args[0], Decimal(args[1])
    except (IndexError, InvalidOperation):
        logger.error(USAGE)
        return 2
    note = " ".join(args[2:]) or None
    with Session(create_db_engine()) as session, session.begin():
        record_cash(session, kind, amount, note, datetime.now(UTC))
        capital = real_capital(session)
    logger.info("Real: %s %s; капитал теперь %s", kind, amount, capital)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
