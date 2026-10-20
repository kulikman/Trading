"""Company: market capitalisation in millions USD (from Finnhub /stock/profile2).

Revision ID: 0025
Revises: 0024
Create Date: 2026-10-20 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0025"
down_revision: str | Sequence[str] | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("company", sa.Column("market_cap_usd_m", sa.Double(), nullable=True))


def downgrade() -> None:
    op.drop_column("company", "market_cap_usd_m")
