"""Telegram: shown card state and skip message id (T18).

Revision ID: 0019
Revises: 0018
Create Date: 2026-10-15 14:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0019"
down_revision: str | Sequence[str] | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("trade_card", sa.Column("tg_state", sa.Text(), nullable=True))
    op.add_column("decision", sa.Column("tg_message_id", sa.BigInteger(), nullable=True))
    # До этой миграции правок и сообщений о пропуске не было — задним числом не рассылать.
    op.execute("UPDATE trade_card SET tg_state = state WHERE tg_message_id IS NOT NULL")
    op.execute("UPDATE decision SET tg_message_id = -1 WHERE status = 'SKIPPED'")


def downgrade() -> None:
    op.drop_column("decision", "tg_message_id")
    op.drop_column("trade_card", "tg_state")
