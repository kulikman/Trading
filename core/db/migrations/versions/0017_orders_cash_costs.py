"""ManualBroker orders, Real cash movements, trade costs (T17).

Revision ID: 0017
Revises: 0016
Create Date: 2026-10-15 12:00:00

"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0017"
down_revision: str | Sequence[str] | None = "0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column[datetime]]:
    return [
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
    ]


def upgrade() -> None:
    op.create_table(
        "broker_order",
        sa.Column("order_id", sa.Text(), nullable=False),
        sa.Column("client_order_id", sa.Text(), nullable=False),
        sa.Column("card_id", sa.BigInteger(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("fill", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "status IN ('pending', 'filled', 'cancelled')", name=op.f("ck_broker_order_status")
        ),
        sa.ForeignKeyConstraint(
            ["card_id"], ["trade_card.id"], name=op.f("fk_broker_order_card_id_trade_card")
        ),
        sa.PrimaryKeyConstraint("order_id", name=op.f("pk_broker_order")),
        sa.UniqueConstraint("client_order_id", name=op.f("uq_broker_order_client_order_id")),
    )
    op.create_table(
        "cash_movement",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("account", sa.Text(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("amount", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        *_timestamps(),
        sa.CheckConstraint("account IN ('real')", name=op.f("ck_cash_movement_account")),
        sa.CheckConstraint("amount <> 0", name=op.f("ck_cash_movement_nonzero")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cash_movement")),
    )
    op.add_column(
        "trade_card", sa.Column("costs", sa.Numeric(precision=18, scale=4), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("trade_card", "costs")
    op.drop_table("cash_movement")
    op.drop_table("broker_order")
