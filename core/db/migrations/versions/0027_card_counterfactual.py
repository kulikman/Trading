"""TradeCard: shadow market entry for a cancelled paper entry (data collection).

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-23 12:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0027"
down_revision: str | Sequence[str] | None = "0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trade_card", sa.Column("counterfactual", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("trade_card", "counterfactual")
