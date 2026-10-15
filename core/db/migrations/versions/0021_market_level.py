"""Market level: Black Swan level on each trading day close (E2d, daily job market-daily).

Revision ID: 0021
Revises: 0020
Create Date: 2026-10-15 17:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0021"
down_revision: str | Sequence[str] | None = "0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "market_level",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("level", sa.Text(), nullable=False),
        sa.Column("vix", sa.Double(), nullable=True),
        sa.Column("spy", sa.Double(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "level IN ('green', 'yellow', 'orange', 'red')", name=op.f("ck_market_level_level")
        ),
        sa.PrimaryKeyConstraint("day", name=op.f("pk_market_level")),
    )


def downgrade() -> None:
    op.drop_table("market_level")
