"""Add repository_connections table for read-only pilot integration

Revision ID: 005_add_repository_connections
Revises: 004_add_repairs
Create Date: 2026-10-19 19:45:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005_add_repository_connections"
down_revision: Union[str, None] = "004_add_repairs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == "postgresql"

    # Expand alembic_version table to support revision identifiers > 32 characters
    if is_postgres:
        op.execute(sa.text("ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(128);"))

    # Create repository_connections table
    op.create_table(
        "repository_connections",
        sa.Column("id", sa.Uuid(as_uuid=True) if not is_postgres else postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("repo_identifier", sa.String(length=255), nullable=False),
        sa.Column("installation_id", sa.String(length=64), nullable=True),
        sa.Column("read_only", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="CONNECTED"),
        sa.Column("connected_by", sa.String(length=128), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_repository_connections_org_id", "repository_connections", ["org_id"])
    op.create_index("ix_repository_connections_status", "repository_connections", ["status"])


def downgrade() -> None:
    op.drop_index("ix_repository_connections_status", table_name="repository_connections")
    op.drop_index("ix_repository_connections_org_id", table_name="repository_connections")
    op.drop_table("repository_connections")
