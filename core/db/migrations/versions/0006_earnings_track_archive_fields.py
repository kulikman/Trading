"""earnings_track: fiscal quarter end (key to SEC revenue) and 8-K date check (T11).

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-14 15:17:42.667162

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("earnings_track", sa.Column("fiscal_period_end", sa.Date(), nullable=True))
    op.add_column("earnings_track", sa.Column("sec_filing_date", sa.Date(), nullable=True))
    op.add_column("earnings_track", sa.Column("date_check", sa.Text(), nullable=True))
    op.create_check_constraint(
        op.f("ck_earnings_track_date_check"),
        "earnings_track",
        "date_check IN ('ok', 'mismatch', 'no_8k')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_earnings_track_date_check"), "earnings_track", type_="check")
    op.drop_column("earnings_track", "date_check")
    op.drop_column("earnings_track", "sec_filing_date")
    op.drop_column("earnings_track", "fiscal_period_end")
