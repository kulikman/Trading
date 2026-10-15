"""Decision per strategy: several paper entries per event (owner decision 15.10.2026).

Revision ID: 0015
Revises: 0014
Create Date: 2026-10-15 09:30:00

"""

from collections.abc import Sequence

from alembic import op

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0015"
down_revision: str | Sequence[str] | None = "0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(op.f("uq_decision_event_id"), "decision", type_="unique")
    # NULLS NOT DISTINCT: у события один итог без стратегии (SKIPPED), входы — по одному на стратегию.
    op.create_unique_constraint(
        op.f("uq_decision_event_id_strategy_id"),
        "decision",
        ["event_id", "strategy_id"],
        postgresql_nulls_not_distinct=True,
    )
    op.create_index(op.f("ix_decision_event_id"), "decision", ["event_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_decision_event_id"), table_name="decision")
    op.drop_constraint(op.f("uq_decision_event_id_strategy_id"), "decision", type_="unique")
    op.create_unique_constraint(op.f("uq_decision_event_id"), "decision", ["event_id"])
