"""Decision steps: each strategy's proposal or skip per event job (T16).

Revision ID: 0014
Revises: 0013
Create Date: 2026-10-15 01:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "decision_step",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("job", sa.Text(), nullable=False),
        sa.Column("strategy_id", sa.Text(), nullable=False),
        sa.Column("is_shadow", sa.Boolean(), nullable=False),
        sa.Column("outcome", sa.Text(), nullable=False),
        sa.Column("mode", sa.Text(), nullable=True),
        sa.Column("construction", sa.Text(), nullable=True),
        sa.Column(
            "reasons", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("edge", sa.Double(), nullable=True),
        sa.Column("confidence", sa.Double(), nullable=True),
        sa.Column("probability", sa.Double(), nullable=True),
        sa.Column("cost_fraction", sa.Double(), nullable=True),
        sa.Column("risk_fraction", sa.Double(), nullable=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
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
            "outcome IN ('proposal', 'skip')", name=op.f("ck_decision_step_outcome")
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["event.id"], name=op.f("fk_decision_step_event_id_event")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decision_step")),
        sa.UniqueConstraint(
            "event_id",
            "stage",
            "job",
            "strategy_id",
            name=op.f("uq_decision_step_event_id_stage_job_strategy_id"),
        ),
    )
    op.create_index(op.f("ix_decision_step_event_id"), "decision_step", ["event_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_decision_step_event_id"), table_name="decision_step")
    op.drop_table("decision_step")
