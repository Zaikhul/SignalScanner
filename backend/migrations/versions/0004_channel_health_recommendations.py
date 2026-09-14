"""Add Channel Health and Recommendation Engine tables (v1.2)

Revision ID: 0004_channel_health
Revises: 0003_trust_layer
Create Date: 2026-09-07 20:00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0004_channel_health"
down_revision: Union[str, None] = "0003_trust_layer"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create channel_health_snapshots table
    op.create_table(
        "channel_health_snapshots",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("band", sa.String(32), server_default="2.4GHz", nullable=False),
        sa.Column("channel_width_mhz", sa.Integer(), server_default="20", nullable=False),
        sa.Column("observation_window", sa.JSON(), nullable=False),
        sa.Column("regulatory_domain", sa.JSON(), nullable=False),
        sa.Column("channels_data", sa.JSON(), nullable=False),
        sa.Column("quality_flags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_channel_health_snapshots_session_id", "channel_health_snapshots", ["session_id"])

    # 2. Create channel_recommendations table
    op.create_table(
        "channel_recommendations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("snapshot_id", sa.String(64), sa.ForeignKey("channel_health_snapshots.id", ondelete="CASCADE"), nullable=False),
        sa.Column("algorithm_version", sa.String(32), server_default="channel-health-1.0.0", nullable=False),
        sa.Column("primary_channel", sa.JSON(), nullable=False),
        sa.Column("alternatives", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.String(16), server_default="medium", nullable=False),
        sa.Column("confidence_reasons", sa.JSON(), nullable=False),
        sa.Column("missing_evidence", sa.JSON(), nullable=False),
        sa.Column("supporting_factors", sa.JSON(), nullable=False),
        sa.Column("counter_signals", sa.JSON(), nullable=False),
        sa.Column("conflict_detected", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_channel_recommendations_session_id", "channel_recommendations", ["session_id"])
    op.create_index("ix_channel_recommendations_snapshot_id", "channel_recommendations", ["snapshot_id"])

    # 3. Create channel_validation_runs table
    op.create_table(
        "channel_validation_runs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("baseline_recommendation_id", sa.String(64), sa.ForeignKey("channel_recommendations.id", ondelete="SET NULL"), nullable=True),
        sa.Column("marker_id", sa.String(64), sa.ForeignKey("session_markers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("before_window", sa.JSON(), nullable=False),
        sa.Column("after_window", sa.JSON(), nullable=False),
        sa.Column("metric_deltas", sa.JSON(), nullable=False),
        sa.Column("summary_label", sa.String(256), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_channel_validation_runs_session_id", "channel_validation_runs", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_channel_validation_runs_session_id", table_name="channel_validation_runs")
    op.drop_table("channel_validation_runs")

    op.drop_index("ix_channel_recommendations_snapshot_id", table_name="channel_recommendations")
    op.drop_index("ix_channel_recommendations_session_id", table_name="channel_recommendations")
    op.drop_table("channel_recommendations")

    op.drop_index("ix_channel_health_snapshots_session_id", table_name="channel_health_snapshots")
    op.drop_table("channel_health_snapshots")
