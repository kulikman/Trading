"""Plugin stage change journal: promote transitions and refusals (T13).

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-14 19:37:40.672575

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plugin_stage_change",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("plugin_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("from_stage", sa.Text(), nullable=False),
        sa.Column("to_stage", sa.Text(), nullable=True),
        sa.Column("accepted", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("metric", sa.Text(), nullable=False),
        sa.Column("observations", sa.Integer(), nullable=False),
        sa.Column("baseline", sa.Double(), nullable=True),
        sa.Column("candidate", sa.Double(), nullable=True),
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
            "from_stage IN ('shadow', 'paper', 'live_small', 'live')",
            name=op.f("ck_plugin_stage_change_from_stage"),
        ),
        sa.CheckConstraint(
            "metric IN ('brier', 'sharpe')", name=op.f("ck_plugin_stage_change_metric")
        ),
        sa.CheckConstraint(
            "to_stage IN ('shadow', 'paper', 'live_small', 'live')",
            name=op.f("ck_plugin_stage_change_to_stage"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plugin_stage_change")),
    )
    op.create_index(
        op.f("ix_plugin_stage_change_plugin_id"), "plugin_stage_change", ["plugin_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_plugin_stage_change_plugin_id"), table_name="plugin_stage_change")
    op.drop_table("plugin_stage_change")
