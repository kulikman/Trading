"""TradeCard: plan of a paper stock entry (limit, stop, shares) shown in the signal.

Revision ID: 0026
Revises: 0025
Create Date: 2026-10-23 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0026"
down_revision: str | Sequence[str] | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trade_card", sa.Column("plan", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("trade_card", "plan")
