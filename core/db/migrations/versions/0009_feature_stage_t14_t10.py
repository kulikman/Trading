"""Feature stages T-14 and T-10 for sector and consensus agents (T14).

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-14 20:00:00

"""

from collections.abc import Sequence

from alembic import op

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("feature_snapshot", "forecast")
NEW = "stage IN ('T-14', 'T-10', 'T-7', 'T-3', 'T-1', 'T0')"
OLD = "stage IN ('T-7', 'T-3', 'T-1', 'T0')"


def _replace(condition: str) -> None:
    for table in TABLES:
        name = op.f(f"ck_{table}_stage")
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, condition)


def upgrade() -> None:
    _replace(NEW)


def downgrade() -> None:
    _replace(OLD)
