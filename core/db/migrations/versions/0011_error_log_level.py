"""Error log level: error or ok (a job works again after a failure).

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-14 22:40:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "error_log",
        sa.Column("level", sa.Text(), server_default="error", nullable=False),
    )
    op.create_check_constraint(op.f("ck_error_log_level"), "error_log", "level IN ('error', 'ok')")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_error_log_level"), "error_log", type_="check")
    op.drop_column("error_log", "level")
