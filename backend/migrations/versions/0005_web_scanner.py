"""Add Web Scanner tables (Ghost Web Scanner integration).

Revision ID: 0005_web_scanner
Revises: 0004_channel_health
Create Date: 2026-10-03 14:30:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "0005_web_scanner"
down_revision: Union[str, None] = "0004_channel_health"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    # 1. web_scan_scopes
    if "web_scan_scopes" not in tables:
        op.create_table(
            "web_scan_scopes",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default_tenant"),
            sa.Column("authorization_reference", sa.String(128), nullable=False),
            sa.Column("assigned_principals", sa.JSON(), nullable=False),
            sa.Column("rules", sa.JSON(), nullable=False),
            sa.Column("budget", sa.JSON(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("scope_hash", sa.String(64), nullable=False),
            sa.Column("allow_tls_unverified", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("allow_geolocation", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("allow_load", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("allow_header_variants", sa.Boolean(), nullable=False, server_default=sa.text("false")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_by", sa.String(64), nullable=False, server_default="admin"),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_web_scan_scopes_tenant_created", "web_scan_scopes", ["tenant_id", "created_at"])

    # 2. web_scan_jobs
    if "web_scan_jobs" not in tables:
        op.create_table(
            "web_scan_jobs",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default_tenant"),
            sa.Column("created_by", sa.String(64), nullable=False, server_default="operator"),
            sa.Column("idempotency_key", sa.String(128), nullable=True),
            sa.Column("idempotency_hash", sa.String(64), nullable=True),
            sa.Column("scope_id", sa.String(64), sa.ForeignKey("web_scan_scopes.id", ondelete="SET NULL"), nullable=True),
            sa.Column("scope_revision", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("scope_hash", sa.String(64), nullable=False, server_default="inline_scope"),
            sa.Column("raw_target", sa.Text(), nullable=False),
            sa.Column("normalized_target", sa.Text(), nullable=False),
            sa.Column("target_display", sa.String(256), nullable=False),
            sa.Column("requested_configuration", sa.JSON(), nullable=False),
            sa.Column("effective_configuration", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
            sa.Column("status_reason", sa.Text(), nullable=True),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("snapshot_sequence", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("summary_data", sa.JSON(), nullable=False),
            sa.UniqueConstraint("tenant_id", "created_by", "idempotency_key", name="uq_web_scan_jobs_idempotency"),
        )
        op.create_index("ix_web_scan_jobs_tenant_created", "web_scan_jobs", ["tenant_id", "created_at"])
        op.create_index("ix_web_scan_jobs_status_queued", "web_scan_jobs", ["status", "queued_at"])

    # 3. web_scan_observations
    if "web_scan_observations" not in tables:
        op.create_table(
            "web_scan_observations",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("scan_id", sa.String(64), sa.ForeignKey("web_scan_jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("module", sa.String(32), nullable=False),
            sa.Column("kind", sa.String(32), nullable=False),
            sa.Column("request_id", sa.String(64), nullable=True),
            sa.Column("data", sa.JSON(), nullable=False),
            sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_web_scan_obs_scan_kind", "web_scan_observations", ["scan_id", "kind"])
        op.create_index("ix_web_scan_obs_scan_time", "web_scan_observations", ["scan_id", "observed_at"])

    # 4. web_scan_findings
    if "web_scan_findings" not in tables:
        op.create_table(
            "web_scan_findings",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("scan_id", sa.String(64), sa.ForeignKey("web_scan_jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("module", sa.String(32), nullable=False),
            sa.Column("check_id", sa.String(64), nullable=False),
            sa.Column("category", sa.String(64), nullable=False),
            sa.Column("source_category", sa.String(64), nullable=True),
            sa.Column("severity", sa.String(16), nullable=False),
            sa.Column("source_severity", sa.String(16), nullable=True),
            sa.Column("severity_reason", sa.Text(), nullable=False),
            sa.Column("confidence", sa.String(32), nullable=False),
            sa.Column("title", sa.String(256), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("remediation", sa.Text(), nullable=False),
            sa.Column("evidence", sa.JSON(), nullable=False),
            sa.Column("fingerprint", sa.String(64), nullable=False),
            sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("assessment_version", sa.String(32), nullable=False, server_default="web_scan.v1"),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("scan_id", "fingerprint", name="uq_web_scan_findings_fingerprint"),
        )
        op.create_index("ix_web_scan_findings_scan_sev", "web_scan_findings", ["scan_id", "severity"])
        op.create_index("ix_web_scan_findings_scan_time", "web_scan_findings", ["scan_id", "first_seen_at"])

    # 5. web_scan_events
    if "web_scan_events" not in tables:
        op.create_table(
            "web_scan_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("scan_id", sa.String(64), sa.ForeignKey("web_scan_jobs.id", ondelete="CASCADE"), nullable=False),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("type", sa.String(32), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("scan_id", "sequence", name="uq_web_scan_events_scan_seq"),
        )
        op.create_index("ix_web_scan_events_scan_seq", "web_scan_events", ["scan_id", "sequence"])

    # 6. web_scan_audit
    if "web_scan_audit" not in tables:
        op.create_table(
            "web_scan_audit",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("tenant_id", sa.String(64), nullable=False, server_default="default_tenant"),
            sa.Column("principal_id", sa.String(64), nullable=False, server_default="operator"),
            sa.Column("scan_id", sa.String(64), nullable=True),
            sa.Column("action", sa.String(64), nullable=False),
            sa.Column("request_id", sa.String(64), nullable=True),
            sa.Column("details", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_web_scan_audit_tenant_time", "web_scan_audit", ["tenant_id", "created_at"])
        op.create_index("ix_web_scan_audit_scan_action", "web_scan_audit", ["scan_id", "action"])

    # 7. web_scan_ws_tickets
    if "web_scan_ws_tickets" not in tables:
        op.create_table(
            "web_scan_ws_tickets",
            sa.Column("ticket_hash", sa.String(64), primary_key=True),
            sa.Column("scan_id", sa.String(64), nullable=False),
            sa.Column("principal_id", sa.String(64), nullable=False),
            sa.Column("tenant_id", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_web_scan_ws_tickets_scan_exp", "web_scan_ws_tickets", ["scan_id", "expires_at"])


def downgrade() -> None:
    op.drop_table("web_scan_ws_tickets")
    op.drop_table("web_scan_audit")
    op.drop_table("web_scan_events")
    op.drop_table("web_scan_findings")
    op.drop_table("web_scan_observations")
    op.drop_table("web_scan_jobs")
    op.drop_table("web_scan_scopes")
