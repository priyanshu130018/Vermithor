"""Add pilot_onboarding_and_governance tables (telemetry_integrations, pilot_governance_policies, pilot_audit_logs)

Revision ID: 007_add_pilot_onboarding_and_governance
Revises: 006_add_investigation_feedback
Create Date: 2026-10-20 17:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007_add_pilot_onboarding_and_governance"
down_revision: Union[str, None] = "006_add_investigation_feedback"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == "postgresql"
    uuid_type = postgresql.UUID(as_uuid=True) if is_postgres else sa.Uuid(as_uuid=True)
    json_type = postgresql.JSONB(astext_type=sa.Text()) if is_postgres else sa.JSON()

    # 1. telemetry_integrations table
    op.create_table(
        "telemetry_integrations",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("integration_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("endpoint_url", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="NOT_CONFIGURED"),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.String(length=128), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("auth_type", sa.String(length=32), nullable=False, server_default="NONE"),
        sa.Column("auth_credentials_masked", sa.String(length=128), nullable=True),
        sa.Column("telemetry_provenance", sa.String(length=64), nullable=False, server_default="NOT_VERIFIED"),
        sa.Column("config_metadata", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_telemetry_integrations_org_id", "telemetry_integrations", ["org_id"])
    op.create_index("ix_telemetry_integrations_integration_type", "telemetry_integrations", ["integration_type"])
    op.create_index("ix_telemetry_integrations_status", "telemetry_integrations", ["status"])

    # 2. pilot_governance_policies table
    op.create_table(
        "pilot_governance_policies",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("org_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("onboarding_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("current_onboarding_step", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("completed_steps_json", json_type, nullable=True),
        sa.Column("collection_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("investigations_paused", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("allow_external_llm", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("redact_sensitive_fields", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("retention_days", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("acknowledged_read_only", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("acknowledged_by", sa.String(length=128), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_pilot_governance_policies_org_id", "pilot_governance_policies", ["org_id"])

    # 3. pilot_audit_logs table
    op.create_table(
        "pilot_audit_logs",
        sa.Column("id", uuid_type, primary_key=True),
        sa.Column("org_id", sa.String(length=64), nullable=False),
        sa.Column("actor_sub", sa.String(length=128), nullable=False),
        sa.Column("actor_role", sa.String(length=64), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("details_json", json_type, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_pilot_audit_logs_org_id", "pilot_audit_logs", ["org_id"])
    op.create_index("ix_pilot_audit_logs_action", "pilot_audit_logs", ["action"])


def downgrade() -> None:
    op.drop_index("ix_pilot_audit_logs_action", table_name="pilot_audit_logs")
    op.drop_index("ix_pilot_audit_logs_org_id", table_name="pilot_audit_logs")
    op.drop_table("pilot_audit_logs")

    op.drop_index("ix_pilot_governance_policies_org_id", table_name="pilot_governance_policies")
    op.drop_table("pilot_governance_policies")

    op.drop_index("ix_telemetry_integrations_status", table_name="telemetry_integrations")
    op.drop_index("ix_telemetry_integrations_integration_type", table_name="telemetry_integrations")
    op.drop_index("ix_telemetry_integrations_org_id", table_name="telemetry_integrations")
    op.drop_table("telemetry_integrations")
