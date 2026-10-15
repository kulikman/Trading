"""Shadow trades: result of proposals that did not become entries (T16, SPEC §10).

Revision ID: 0016
Revises: 0015
Create Date: 2026-10-15 10:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0016"
down_revision: str | Sequence[str] | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shadow_trade",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("strategy_id", sa.Text(), nullable=False),
        sa.Column("step_id", sa.BigInteger(), nullable=False),
        sa.Column("construction", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("entry_on", sa.Date(), nullable=True),
        sa.Column("exit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_reason", sa.Text(), nullable=True),
        sa.Column("return_on_risk", sa.Double(), nullable=True),
        sa.Column("pnl", sa.Double(), nullable=True),
        sa.Column("brier", sa.Double(), nullable=True),
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
            "status IN ('closed', 'open', 'no_data', 'scored')",
            name=op.f("ck_shadow_trade_status"),
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["event.id"], name=op.f("fk_shadow_trade_event_id_event")
        ),
        sa.ForeignKeyConstraint(
            ["step_id"], ["decision_step.id"], name=op.f("fk_shadow_trade_step_id_decision_step")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shadow_trade")),
        sa.UniqueConstraint(
            "event_id", "strategy_id", name=op.f("uq_shadow_trade_event_id_strategy_id")
        ),
    )
    op.create_index(op.f("ix_shadow_trade_event_id"), "shadow_trade", ["event_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_shadow_trade_event_id"), table_name="shadow_trade")
    op.drop_table("shadow_trade")
