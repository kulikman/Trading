"""Trade card: risk in dollars for Real cards (E10, sized from Real capital).

Revision ID: 0022
Revises: 0021
Create Date: 2026-10-15 20:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0022"
down_revision: str | Sequence[str] | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trade_card", sa.Column("risk_usd", sa.Numeric(18, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("trade_card", "risk_usd")
