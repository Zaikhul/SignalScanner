"""Add Measurement Trust Layer tables and columns (FQ-01, PROV-01, CHAN-01, PRIV-01)

Revision ID: 0003_trust_layer
Revises: 0002_freq_bigint
Create Date: 2026-08-25 14:30:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0003_trust_layer"
down_revision: Union[str, None] = "0002_freq_bigint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add columns to measurements
    op.add_column("measurements", sa.Column("scan_id", sa.String(64), nullable=True))
    op.add_column("measurements", sa.Column("trace_id", sa.String(64), nullable=True))
    op.add_column("measurements", sa.Column("freshness", sa.String(32), server_default="fresh", nullable=False))
    op.add_column("measurements", sa.Column("source_method", sa.String(64), server_default="unknown", nullable=False))
    op.add_column("measurements", sa.Column("rssi_processing", sa.String(32), server_default="unknown", nullable=False))

    # 2. Create session_manifests table
    op.create_table(
        "session_manifests",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("manifest_version", sa.String(16), nullable=False, server_default="1.0"),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_session_manifests_session_id", "session_manifests", ["session_id"])

    # 3. Create channel_metrics table
    op.create_table(
        "channel_metrics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel", sa.Integer(), nullable=False),
        sa.Column("metric_type", sa.String(64), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("unit", sa.String(32), nullable=False, server_default="ratio"),
        sa.Column("evidence", sa.String(32), nullable=False, server_default="inferred"),
        sa.Column("method", sa.String(64), nullable=False, server_default="weighted_bssid_overlap_v2"),
        sa.Column("window_ms", sa.Integer(), nullable=False, server_default="10000"),
        sa.Column("uncertainty", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_channel_metrics_session_id", "channel_metrics", ["session_id"])

    # 4. Create export_audit_logs table
    op.create_table(
        "export_audit_logs",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("session_id", sa.String(64), sa.ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("format", sa.String(16), nullable=False, server_default="json"),
        sa.Column("scope", sa.String(64), nullable=False, server_default="full_session"),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("exported_by", sa.String(64), nullable=False, server_default="anonymous_user"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_export_audit_logs_session_id", "export_audit_logs", ["session_id"])


def downgrade() -> None:
    op.drop_table("export_audit_logs")
    op.drop_table("channel_metrics")
    op.drop_table("session_manifests")
    op.drop_column("measurements", "rssi_processing")
    op.drop_column("measurements", "source_method")
    op.drop_column("measurements", "freshness")
    op.drop_column("measurements", "trace_id")
    op.drop_column("measurements", "scan_id")
