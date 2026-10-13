"""News articles per ticker for the company profile (DASHBOARD.md 4.5), T06.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-13 23:12:52.473793

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "news_article",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("tickers", postgresql.ARRAY(sa.Text()), nullable=False),
        sa.Column("publisher", sa.Text(), nullable=True),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("keywords", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("insights", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tags", postgresql.ARRAY(sa.Text()), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_news_article")),
    )
    op.create_index(
        op.f("ix_news_article_published_at"), "news_article", ["published_at"], unique=False
    )
    op.create_index(
        "ix_news_article_tickers", "news_article", ["tickers"], unique=False, postgresql_using="gin"
    )


def downgrade() -> None:
    op.drop_index("ix_news_article_tickers", table_name="news_article", postgresql_using="gin")
    op.drop_index(op.f("ix_news_article_published_at"), table_name="news_article")
    op.drop_table("news_article")
