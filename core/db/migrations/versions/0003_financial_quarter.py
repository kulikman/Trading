"""Quarterly financials from SEC XBRL for the company profile (DASHBOARD.md 4.5), T07.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-13 23:46:35.484495

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "financial_quarter",
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("value", sa.Double(), nullable=False),
        sa.Column("unit", sa.Text(), nullable=False),
        sa.Column("derived", sa.Boolean(), nullable=False),
        sa.Column("concept", sa.Text(), nullable=False),
        sa.Column("form", sa.Text(), nullable=False),
        sa.Column("accession", sa.Text(), nullable=False),
        sa.Column("filed", sa.Date(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["ticker"], ["company.ticker"], name=op.f("fk_financial_quarter_ticker_company")
        ),
        sa.PrimaryKeyConstraint(
            "ticker", "metric", "period_end", name=op.f("pk_financial_quarter")
        ),
    )


def downgrade() -> None:
    op.drop_table("financial_quarter")
