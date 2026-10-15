"""Trade card: reminder sent when a Real fill is not confirmed in 15 minutes (T18).

Revision ID: 0020
Revises: 0019
Create Date: 2026-10-15 15:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0020"
down_revision: str | Sequence[str] | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trade_card", sa.Column("reminded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("trade_card", "reminded_at")
