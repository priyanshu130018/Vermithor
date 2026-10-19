"""Add repairs table and key sequence

Revision ID: 004_add_repairs
Revises: 003_add_investigations
Create Date: 2026-10-19 16:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004_add_repairs"
down_revision: Union[str, None] = "003_add_investigations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == "postgresql"

    if is_postgres:
        op.execute("CREATE SEQUENCE IF NOT EXISTS repair_key_seq START 1;")

    # Create repairs table
    op.create_table(
        "repairs",
        sa.Column("id", sa.Uuid(as_uuid=True) if not is_postgres else postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("repair_key", sa.String(length=64), nullable=False),
        sa.Column("investigation_key", sa.String(length=64), nullable=False),
        sa.Column("incident_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("repository_url", sa.String(length=255), nullable=True),
        sa.Column("base_commit", sa.String(length=64), nullable=True),
        sa.Column("target_branch", sa.String(length=128), nullable=False, server_default="main"),
        sa.Column("repair_branch", sa.String(length=128), nullable=True),
        sa.Column("suspected_defect", sa.Text(), nullable=True),
        sa.Column("evidence_citations", postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(), nullable=True),
        sa.Column("inspected_files", postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(), nullable=True),
        sa.Column("proposed_patch", sa.Text(), nullable=True),
        sa.Column("patch_hash", sa.String(length=64), nullable=True),
        sa.Column("files_changed", postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(), nullable=True),
        sa.Column("test_commands", postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(), nullable=True),
        sa.Column("test_results", postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(), nullable=True),
        sa.Column("validation_status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("pull_request_url", sa.String(length=255), nullable=True),
        sa.Column("pull_request_number", sa.Integer(), nullable=True),
        sa.Column("requires_human_approval", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("approval_status", sa.String(length=32), nullable=False, server_default="PENDING"),
        sa.Column("approved_by", sa.String(length=128), nullable=True),
        sa.Column("approval_notes", sa.Text(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_provider", sa.String(length=64), nullable=False, server_default="unknown"),
        sa.Column("model_name", sa.String(length=128), nullable=True),
        sa.Column("is_fallback", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("iteration_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("report_json", postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_repairs_repair_key", "repairs", ["repair_key"], unique=True)
    op.create_index("ix_repairs_investigation_key", "repairs", ["investigation_key"])
    op.create_index("ix_repairs_incident_key", "repairs", ["incident_key"])
    op.create_index("ix_repairs_status", "repairs", ["status"])


def downgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == "postgresql"

    op.drop_index("ix_repairs_status", table_name="repairs")
    op.drop_index("ix_repairs_incident_key", table_name="repairs")
    op.drop_index("ix_repairs_investigation_key", table_name="repairs")
    op.drop_index("ix_repairs_repair_key", table_name="repairs")
    op.drop_table("repairs")

    if is_postgres:
        op.execute("DROP SEQUENCE IF EXISTS repair_key_seq;")
