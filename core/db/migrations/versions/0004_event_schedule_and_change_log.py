"""Event job schedule, event change log, APScheduler job store, event.fiscal_period (T09).

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-14 11:31:27.325722

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "apscheduler_jobs",
        sa.Column("id", sa.Unicode(length=191), nullable=False),
        sa.Column("next_run_time", sa.Float(precision=25), nullable=True),
        sa.Column("job_state", sa.LargeBinary(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_apscheduler_jobs")),
    )
    op.create_index(
        op.f("ix_apscheduler_jobs_next_run_time"),
        "apscheduler_jobs",
        ["next_run_time"],
        unique=False,
    )
    op.create_table(
        "event_change",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("field", sa.Text(), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
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
            ["event_id"], ["event.id"], name=op.f("fk_event_change_event_id_event")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_change")),
    )
    op.create_index(op.f("ix_event_change_event_id"), "event_change", ["event_id"], unique=False)
    op.create_table(
        "event_job",
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("job", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.Text(), server_default="planned", nullable=False),
        sa.Column("outside_session", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
            "kind IN ('analysis', 'execution', 'notify')", name=op.f("ck_event_job_kind")
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'done', 'failed', 'missed', 'no_handler')",
            name=op.f("ck_event_job_status"),
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["event.id"], name=op.f("fk_event_job_event_id_event")
        ),
        sa.PrimaryKeyConstraint("event_id", "stage", "job", name=op.f("pk_event_job")),
    )
    op.create_index(op.f("ix_event_job_run_at"), "event_job", ["run_at"], unique=False)
    op.add_column("event", sa.Column("fiscal_period", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("event", "fiscal_period")
    op.drop_index(op.f("ix_event_job_run_at"), table_name="event_job")
    op.drop_table("event_job")
    op.drop_index(op.f("ix_event_change_event_id"), table_name="event_change")
    op.drop_table("event_change")
    op.drop_index(op.f("ix_apscheduler_jobs_next_run_time"), table_name="apscheduler_jobs")
    op.drop_table("apscheduler_jobs")
