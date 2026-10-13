"""Initial schema: SPEC §5 tables with created_at/updated_at, CHECKs from core.domain.types.

Revision ID: 0001
Revises:
Create Date: 2026-10-13 21:34:25.957002

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# Alembic reads these module attributes; __all__ marks them as used for static analysis.
__all__ = ["branch_labels", "depends_on", "down_revision", "downgrade", "revision", "upgrade"]

revision: str = "0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "plugin",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("weight", sa.Double(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
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
        sa.CheckConstraint("kind IN ('agent', 'strategy')", name=op.f("ck_plugin_kind")),
        sa.CheckConstraint(
            "stage IN ('shadow', 'paper', 'live_small', 'live')", name=op.f("ck_plugin_stage")
        ),
        sa.CheckConstraint("weight BETWEEN 0 AND 1", name=op.f("ck_plugin_weight")),
        sa.PrimaryKeyConstraint("id", "version", name=op.f("pk_plugin")),
    )
    op.create_table(
        "sector",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("key_metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("macro_sensitivity", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("data_sources", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sector")),
    )
    op.create_table(
        "company",
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("sector_id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("overview", sa.Text(), nullable=True),
        sa.Column("segments", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("risks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("options_liquid", sa.Boolean(), nullable=True),
        sa.Column("calibration_status", sa.Text(), server_default="active", nullable=False),
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
            "calibration_status IN ('active', 'quarantine')",
            name=op.f("ck_company_calibration_status"),
        ),
        sa.ForeignKeyConstraint(
            ["sector_id"], ["sector.id"], name=op.f("fk_company_sector_id_sector")
        ),
        sa.PrimaryKeyConstraint("ticker", name=op.f("pk_company")),
    )
    op.create_index(op.f("ix_company_sector_id"), "company", ["sector_id"], unique=False)
    op.create_table(
        "sector_summary",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("sector_id", sa.Text(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("trend", sa.SmallInteger(), nullable=True),
        sa.Column("confidence", sa.Double(), nullable=True),
        sa.Column("peer_surprise_mean", sa.Double(), nullable=True),
        sa.Column("sector_momentum_30d", sa.Double(), nullable=True),
        sa.Column("facts", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("risks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("text_summary", sa.Text(), nullable=True),
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
        sa.CheckConstraint("confidence BETWEEN 0 AND 1", name=op.f("ck_sector_summary_confidence")),
        sa.CheckConstraint("trend IN (-1, 0, 1)", name=op.f("ck_sector_summary_trend")),
        sa.ForeignKeyConstraint(
            ["sector_id"], ["sector.id"], name=op.f("fk_sector_summary_sector_id_sector")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sector_summary")),
    )
    op.create_index(
        op.f("ix_sector_summary_sector_id"), "sector_summary", ["sector_id"], unique=False
    )
    op.create_table(
        "consensus_snapshot",
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("fiscal_period", sa.Text(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("eps_estimate", sa.Double(), nullable=True),
        sa.Column("rev_estimate", sa.Double(), nullable=True),
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
            ["ticker"], ["company.ticker"], name=op.f("fk_consensus_snapshot_ticker_company")
        ),
        sa.PrimaryKeyConstraint(
            "ticker", "fiscal_period", "as_of", name=op.f("pk_consensus_snapshot")
        ),
    )
    op.create_table(
        "earnings_track",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("report_time", sa.Text(), nullable=True),
        sa.Column("eps_consensus", sa.Double(), nullable=True),
        sa.Column("eps_actual", sa.Double(), nullable=True),
        sa.Column("eps_surprise_pct", sa.Double(), nullable=True),
        sa.Column("rev_consensus", sa.Double(), nullable=True),
        sa.Column("rev_actual", sa.Double(), nullable=True),
        sa.Column("rev_surprise_pct", sa.Double(), nullable=True),
        sa.Column("guidance_change", sa.SmallInteger(), nullable=True),
        sa.Column("implied_move", sa.Double(), nullable=True),
        sa.Column("actual_move", sa.Double(), nullable=True),
        sa.Column("move_ratio", sa.Double(), nullable=True),
        sa.Column("reaction_cause", sa.Text(), nullable=True),
        sa.Column("model_p_beat", sa.Double(), nullable=True),
        sa.Column("model_p_up", sa.Double(), nullable=True),
        sa.Column("model_move_ratio", sa.Double(), nullable=True),
        sa.Column("decision", sa.Text(), nullable=True),
        sa.Column("skip_reasons", postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column("shadow_pnl", sa.Numeric(precision=18, scale=4), nullable=True),
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
            "decision IN ('ENTERED', 'SKIPPED', 'CANCELLED', 'DATA_FAIL')",
            name=op.f("ck_earnings_track_decision"),
        ),
        sa.CheckConstraint(
            "report_time IN ('BMO', 'AMC', 'DURING')", name=op.f("ck_earnings_track_report_time")
        ),
        sa.CheckConstraint(
            "guidance_change IN (-1, 0, 1)", name=op.f("ck_earnings_track_guidance_change")
        ),
        sa.ForeignKeyConstraint(
            ["ticker"], ["company.ticker"], name=op.f("fk_earnings_track_ticker_company")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_earnings_track")),
        sa.UniqueConstraint(
            "ticker", "report_date", name=op.f("uq_earnings_track_ticker_report_date")
        ),
    )
    op.create_table(
        "event",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("report_time", sa.Text(), nullable=True),
        sa.Column("date_status", sa.Text(), nullable=False),
        sa.Column(
            "date_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("queue_status", sa.Text(), server_default="planned", nullable=False),
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
            "date_status IN ('projected', 'confirmed')", name=op.f("ck_event_date_status")
        ),
        sa.CheckConstraint(
            "queue_status IN ('planned', 'profiling', 'signals', 'decided', 'done')",
            name=op.f("ck_event_queue_status"),
        ),
        sa.CheckConstraint(
            "report_time IN ('BMO', 'AMC', 'DURING')", name=op.f("ck_event_report_time")
        ),
        sa.ForeignKeyConstraint(
            ["ticker"], ["company.ticker"], name=op.f("fk_event_ticker_company")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event")),
        sa.UniqueConstraint("ticker", "report_date", name=op.f("uq_event_ticker_report_date")),
    )
    op.create_table(
        "peer_edge",
        sa.Column("from_ticker", sa.Text(), nullable=False),
        sa.Column("to_ticker", sa.Text(), nullable=False),
        sa.Column("strength", sa.Double(), nullable=True),
        sa.Column("lag_days", sa.Integer(), nullable=True),
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
        sa.CheckConstraint("from_ticker <> to_ticker", name=op.f("ck_peer_edge_not_self")),
        sa.CheckConstraint("lag_days >= 0", name=op.f("ck_peer_edge_lag_days")),
        sa.CheckConstraint("strength BETWEEN -1 AND 1", name=op.f("ck_peer_edge_strength")),
        sa.ForeignKeyConstraint(
            ["from_ticker"], ["company.ticker"], name=op.f("fk_peer_edge_from_ticker_company")
        ),
        sa.ForeignKeyConstraint(
            ["to_ticker"], ["company.ticker"], name=op.f("fk_peer_edge_to_ticker_company")
        ),
        sa.PrimaryKeyConstraint("from_ticker", "to_ticker", name=op.f("pk_peer_edge")),
    )
    op.create_table(
        "report_audit",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("ticker", sa.Text(), nullable=False),
        sa.Column("fiscal_period", sa.Text(), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("segments_expected", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("segments_actual", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("guidance", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("management_tone", sa.Double(), nullable=True),
        sa.Column("named_risks", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("source_urls", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            ["ticker"], ["company.ticker"], name=op.f("fk_report_audit_ticker_company")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_report_audit")),
    )
    op.create_index(op.f("ix_report_audit_ticker"), "report_audit", ["ticker"], unique=False)
    op.create_table(
        "decision",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column(
            "reasons", postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'"), nullable=False
        ),
        sa.Column("mode", sa.Text(), nullable=True),
        sa.Column("strategy_id", sa.Text(), nullable=True),
        sa.Column("construction", sa.Text(), nullable=True),
        sa.Column("shadow", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
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
            "status IN ('ENTERED', 'SKIPPED', 'CANCELLED', 'DATA_FAIL')",
            name=op.f("ck_decision_status"),
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["event.id"], name=op.f("fk_decision_event_id_event")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decision")),
        sa.UniqueConstraint("event_id", name=op.f("uq_decision_event_id")),
    )
    op.create_table(
        "feature_snapshot",
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("agent_id", sa.Text(), nullable=False),
        sa.Column("agent_version", sa.Text(), nullable=False),
        sa.Column("features", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
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
            "stage IN ('T-7', 'T-3', 'T-1', 'T0')", name=op.f("ck_feature_snapshot_stage")
        ),
        sa.ForeignKeyConstraint(
            ["event_id"], ["event.id"], name=op.f("fk_feature_snapshot_event_id_event")
        ),
        sa.PrimaryKeyConstraint(
            "event_id", "stage", "agent_id", "agent_version", name=op.f("pk_feature_snapshot")
        ),
    )
    op.create_table(
        "forecast",
        sa.Column("event_id", sa.BigInteger(), nullable=False),
        sa.Column("stage", sa.Text(), nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column("p_beat", sa.Double(), nullable=True),
        sa.Column("p_up", sa.Double(), nullable=True),
        sa.Column("move_ratio", sa.Double(), nullable=True),
        sa.Column("market_p_beat", sa.Double(), nullable=True),
        sa.Column("market_p_up", sa.Double(), nullable=True),
        sa.Column("implied_move", sa.Double(), nullable=True),
        sa.Column("edge_beat", sa.Double(), nullable=True),
        sa.Column("edge_up", sa.Double(), nullable=True),
        sa.Column("edge_move", sa.Double(), nullable=True),
        sa.Column("exploration", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
        sa.CheckConstraint("stage IN ('T-7', 'T-3', 'T-1', 'T0')", name=op.f("ck_forecast_stage")),
        sa.CheckConstraint("market_p_beat BETWEEN 0 AND 1", name=op.f("ck_forecast_market_p_beat")),
        sa.CheckConstraint("market_p_up BETWEEN 0 AND 1", name=op.f("ck_forecast_market_p_up")),
        sa.CheckConstraint("move_ratio BETWEEN 0 AND 1", name=op.f("ck_forecast_move_ratio")),
        sa.CheckConstraint("p_beat BETWEEN 0 AND 1", name=op.f("ck_forecast_p_beat")),
        sa.CheckConstraint("p_up BETWEEN 0 AND 1", name=op.f("ck_forecast_p_up")),
        sa.ForeignKeyConstraint(
            ["event_id"], ["event.id"], name=op.f("fk_forecast_event_id_event")
        ),
        sa.PrimaryKeyConstraint("event_id", "stage", "model_version", name=op.f("pk_forecast")),
    )
    op.create_table(
        "trade_card",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("decision_id", sa.BigInteger(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("paper", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("legs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("stop", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("trailing", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("fills", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("tg_message_id", sa.BigInteger(), nullable=True),
        sa.Column("pnl_total", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("pnl_direction", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("pnl_vol", sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column("pnl_ivcrush", sa.Numeric(precision=18, scale=4), nullable=True),
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
            "state IN ('PLANNED', 'ARMED', 'OPEN', 'C_MODE', 'CLOSING', 'CLOSED', 'CANCELLED', 'STOPPED')",
            name=op.f("ck_trade_card_state"),
        ),
        sa.ForeignKeyConstraint(
            ["decision_id"], ["decision.id"], name=op.f("fk_trade_card_decision_id_decision")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trade_card")),
    )
    op.create_index(op.f("ix_trade_card_decision_id"), "trade_card", ["decision_id"], unique=False)
    op.create_table(
        "trade_card_transition",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("card_id", sa.BigInteger(), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("from_state", sa.Text(), nullable=True),
        sa.Column("to_state", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
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
            "from_state IN ('PLANNED', 'ARMED', 'OPEN', 'C_MODE', 'CLOSING', 'CLOSED', 'CANCELLED', 'STOPPED')",
            name=op.f("ck_trade_card_transition_from_state"),
        ),
        sa.CheckConstraint(
            "to_state IN ('PLANNED', 'ARMED', 'OPEN', 'C_MODE', 'CLOSING', 'CLOSED', 'CANCELLED', 'STOPPED')",
            name=op.f("ck_trade_card_transition_to_state"),
        ),
        sa.ForeignKeyConstraint(
            ["card_id"], ["trade_card.id"], name=op.f("fk_trade_card_transition_card_id_trade_card")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_trade_card_transition")),
    )
    op.create_index(
        op.f("ix_trade_card_transition_card_id"), "trade_card_transition", ["card_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_trade_card_transition_card_id"), table_name="trade_card_transition")
    op.drop_table("trade_card_transition")
    op.drop_index(op.f("ix_trade_card_decision_id"), table_name="trade_card")
    op.drop_table("trade_card")
    op.drop_table("forecast")
    op.drop_table("feature_snapshot")
    op.drop_table("decision")
    op.drop_index(op.f("ix_report_audit_ticker"), table_name="report_audit")
    op.drop_table("report_audit")
    op.drop_table("peer_edge")
    op.drop_table("event")
    op.drop_table("earnings_track")
    op.drop_table("consensus_snapshot")
    op.drop_index(op.f("ix_sector_summary_sector_id"), table_name="sector_summary")
    op.drop_table("sector_summary")
    op.drop_index(op.f("ix_company_sector_id"), table_name="company")
    op.drop_table("company")
    op.drop_table("sector")
    op.drop_table("plugin")
