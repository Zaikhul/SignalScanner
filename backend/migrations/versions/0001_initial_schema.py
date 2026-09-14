"""Initial schema

Revision ID: 0001_initial_schema
Revises: 
Create Date: 2026-08-25 11:42:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Tables are created if they don't exist
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = inspector.get_table_names()

    if "collectors" not in tables:
        op.create_table(
            "collectors",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("platform", sa.String(length=32), nullable=False),
            sa.Column("version", sa.String(length=32), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("public_key", sa.Text(), nullable=True),
            sa.Column("capabilities", sa.JSON(), nullable=False),
            sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    if "scan_sessions" not in tables:
        op.create_table(
            "scan_sessions",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("name", sa.String(length=128), nullable=False),
            sa.Column("mode", sa.String(length=32), nullable=False),
            sa.Column("collector_id", sa.String(length=64), sa.ForeignKey("collectors.id"), nullable=False),
            sa.Column("source_type", sa.String(length=32), server_default="collector", nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False),
            sa.Column("config", sa.JSON(), nullable=False),
            sa.Column("tags", sa.JSON(), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )

    if "targets" not in tables:
        op.create_table(
            "targets",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("session_id", sa.String(length=64), sa.ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("target_id", sa.String(length=64), nullable=False),
            sa.Column("display_name", sa.String(length=128), nullable=True),
            sa.Column("mode", sa.String(length=32), nullable=False),
            sa.Column("channel", sa.Integer(), nullable=True),
            sa.Column("band", sa.String(length=32), nullable=True),
            sa.Column("is_pinned", sa.Boolean(), default=False, nullable=False),
            sa.Column("metadata_json", sa.JSON(), nullable=False),
            sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
            sa.Column("last_seen", sa.DateTime(timezone=True), nullable=False),
        )

    if "measurements" not in tables:
        op.create_table(
            "measurements",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("session_id", sa.String(length=64), sa.ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("target_id", sa.String(length=128), nullable=False),
            sa.Column("target_db_id", sa.String(length=64), sa.ForeignKey("targets.id", ondelete="CASCADE"), nullable=True),
            sa.Column("sequence", sa.Integer(), nullable=False),
            sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("signal_value", sa.Float(), nullable=False),
            sa.Column("unit", sa.String(length=16), nullable=False),
            sa.Column("noise_floor", sa.Float(), nullable=True),
            sa.Column("snr", sa.Float(), nullable=True),
            sa.Column("frequency_hz", sa.Integer(), nullable=True),
            sa.Column("channel", sa.Integer(), nullable=True),
            sa.Column("band", sa.String(length=32), nullable=True),
            sa.Column("quality_flags", sa.JSON(), nullable=False),
            sa.Column("raw_extra", sa.JSON(), nullable=False),
        )

    if "session_markers" not in tables:
        op.create_table(
            "session_markers",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("session_id", sa.String(length=64), sa.ForeignKey("scan_sessions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("label", sa.String(length=128), nullable=False),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    op.drop_table("session_markers")
    op.drop_table("measurements")
    op.drop_table("targets")
    op.drop_table("scan_sessions")
    op.drop_table("collectors")
