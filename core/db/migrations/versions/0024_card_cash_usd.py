"""Trade card: cash a Real position takes from the account (E10-3, position cap).

Revision ID: 0024
Revises: 0023
Create Date: 2026-10-15 22:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0024"
down_revision: str | Sequence[str] | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trade_card", sa.Column("cash_usd", sa.Numeric(18, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("trade_card", "cash_usd")
