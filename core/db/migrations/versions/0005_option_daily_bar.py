"""Option daily bar archive: daily prices of option contracts for the backtest (T10).

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-14 12:48:25.961729

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "option_daily_bar",
        sa.Column("option_ticker", sa.Text(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("underlying", sa.Text(), nullable=False),
        sa.Column("expiration", sa.Date(), nullable=False),
        sa.Column("strike", sa.Double(), nullable=False),
        sa.Column("option_type", sa.Text(), nullable=False),
        sa.Column("open", sa.Double(), nullable=False),
        sa.Column("high", sa.Double(), nullable=False),
        sa.Column("low", sa.Double(), nullable=False),
        sa.Column("close", sa.Double(), nullable=False),
        sa.Column("volume", sa.Double(), nullable=False),
        sa.Column("vwap", sa.Double(), nullable=True),
        sa.Column("transactions", sa.Integer(), nullable=True),
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
            "option_type IN ('call', 'put')", name=op.f("ck_option_daily_bar_option_type")
        ),
        sa.PrimaryKeyConstraint("option_ticker", "day", name=op.f("pk_option_daily_bar")),
    )
    op.create_index(
        "ix_option_daily_bar_underlying_day",
        "option_daily_bar",
        ["underlying", "day"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_option_daily_bar_underlying_day", table_name="option_daily_bar")
    op.drop_table("option_daily_bar")
