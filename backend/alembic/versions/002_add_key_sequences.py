"""Add PostgreSQL key sequences for correlation, incidents, rca, summary, and runbooks

Revision ID: 002_add_key_sequences
Revises: 001_initial_schema
Create Date: 2026-10-18 10:00:00.000000

"""
from typing import Sequence, Union
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_add_key_sequences"
down_revision: Union[str, None] = "001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("CREATE SEQUENCE IF NOT EXISTS correlation_group_key_seq START 1;")
        op.execute("CREATE SEQUENCE IF NOT EXISTS incident_key_seq START 1;")
        op.execute("CREATE SEQUENCE IF NOT EXISTS rca_analysis_key_seq START 1;")
        op.execute("CREATE SEQUENCE IF NOT EXISTS summary_key_seq START 1;")
        op.execute("CREATE SEQUENCE IF NOT EXISTS runbook_key_seq START 1;")


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("DROP SEQUENCE IF EXISTS correlation_group_key_seq;")
        op.execute("DROP SEQUENCE IF EXISTS incident_key_seq;")
        op.execute("DROP SEQUENCE IF EXISTS rca_analysis_key_seq;")
        op.execute("DROP SEQUENCE IF EXISTS summary_key_seq;")
        op.execute("DROP SEQUENCE IF EXISTS runbook_key_seq;")
