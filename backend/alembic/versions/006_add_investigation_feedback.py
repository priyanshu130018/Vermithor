"""Add investigation_feedback table for operator verification feedback

Revision ID: 006_add_investigation_feedback
Revises: 005_add_repository_connections
Create Date: 2026-10-20 11:55:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "006_add_investigation_feedback"
down_revision: Union[str, None] = "005_add_repository_connections"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == "postgresql"

    # Create investigation_feedback table
    op.create_table(
        "investigation_feedback",
        sa.Column("id", sa.Uuid(as_uuid=True) if not is_postgres else postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("investigation_key", sa.String(length=64), nullable=False),
        sa.Column("incident_key", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("feedback_status", sa.String(length=32), nullable=False),
        sa.Column("operator_id", sa.String(length=128), nullable=False),
        sa.Column("confirmed_root_cause", sa.String(length=255), nullable=True),
        sa.Column("evidence_reference", sa.Text(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_investigation_feedback_investigation_key", "investigation_feedback", ["investigation_key"])
    op.create_index("ix_investigation_feedback_incident_key", "investigation_feedback", ["incident_key"])
    op.create_index("ix_investigation_feedback_org_id", "investigation_feedback", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_investigation_feedback_org_id", table_name="investigation_feedback")
    op.drop_index("ix_investigation_feedback_incident_key", table_name="investigation_feedback")
    op.drop_index("ix_investigation_feedback_investigation_key", table_name="investigation_feedback")
    op.drop_table("investigation_feedback")
