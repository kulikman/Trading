"""Trade card: Telegram message asking for the actual fill price (E10-3).

Revision ID: 0023
Revises: 0022
Create Date: 2026-10-15 21:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0023"
down_revision: str | Sequence[str] | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trade_card", sa.Column("fill_prompt_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("trade_card", "fill_prompt_id")
