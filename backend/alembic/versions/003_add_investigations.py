"""Add investigations table and key sequence

Revision ID: 003_add_investigations
Revises: 002_add_key_sequences
Create Date: 2026-10-19 12:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003_add_investigations"
down_revision: Union[str, None] = "002_add_key_sequences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == "postgresql"

    if is_postgres:
        op.execute("CREATE SEQUENCE IF NOT EXISTS investigation_key_seq START 1;")

    # Create investigations table
    op.create_table(
        "investigations",
        sa.Column("id", sa.Uuid(as_uuid=True) if not is_postgres else postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("investigation_key", sa.String(length=64), nullable=False),
        sa.Column("incident_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("target_service", sa.String(length=128), nullable=False, server_default="unknown"),
        sa.Column("environment", sa.String(length=64), nullable=False, server_default="production"),
        sa.Column("leading_hypothesis", sa.String(length=255), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("is_fallback", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("model_provider", sa.String(length=64), nullable=False, server_default="unknown"),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("report_json", postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(), nullable=True),
        sa.Column("evidence_json", postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_investigations_investigation_key", "investigations", ["investigation_key"], unique=True)
    op.create_index("ix_investigations_incident_key", "investigations", ["incident_key"])
    op.create_index("ix_investigations_status", "investigations", ["status"])


def downgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == "postgresql"

    op.drop_index("ix_investigations_status", table_name="investigations")
    op.drop_index("ix_investigations_incident_key", table_name="investigations")
    op.drop_index("ix_investigations_investigation_key", table_name="investigations")
    op.drop_table("investigations")

    if is_postgres:
        op.execute("DROP SEQUENCE IF EXISTS investigation_key_seq;")
