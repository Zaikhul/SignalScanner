"""Alter frequency_hz to BigInteger

Revision ID: 0002_alter_frequency_hz_to_bigint
Revises: 0001_initial_schema
Create Date: 2026-08-25 11:43:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_freq_bigint"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "measurements",
        "frequency_hz",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
        existing_nullable=True,
        postgresql_using="frequency_hz::bigint",
    )


def downgrade() -> None:
    op.alter_column(
        "measurements",
        "frequency_hz",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
        existing_nullable=True,
        postgresql_using="frequency_hz::integer",
    )
