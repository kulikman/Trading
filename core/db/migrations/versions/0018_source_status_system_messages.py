"""Source status and SYSTEM messages journal (T18, DASHBOARD 4.7).

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-15 13:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0018"
down_revision: str | Sequence[str] | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_status",
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("last_ok_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("source", name=op.f("pk_source_status")),
    )
    op.create_table(
        "system_message",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("code", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tg_message_id", sa.BigInteger(), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_system_message")),
    )
    op.create_index(op.f("ix_system_message_at"), "system_message", ["at"], unique=False)
    op.add_column("error_log", sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True))
    # Ошибки до появления сообщений «СИСТЕМА» уже разобраны вручную — не рассылать их задним числом.
    op.execute("UPDATE error_log SET notified_at = at")


def downgrade() -> None:
    op.drop_column("error_log", "notified_at")
    op.drop_index(op.f("ix_system_message_at"), table_name="system_message")
    op.drop_table("system_message")
    op.drop_table("source_status")
