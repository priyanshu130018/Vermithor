"""Add org_id to investigations and repairs tables for multi-tenant isolation

Revision ID: 008_add_org_id_to_investigations_and_repairs
Revises: 007_add_pilot_onboarding_and_governance
Create Date: 2026-10-20 17:35:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "008_add_org_id_to_investigations_and_repairs"
down_revision: Union[str, None] = "007_add_pilot_onboarding_and_governance"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add org_id to investigations
    op.add_column(
        "investigations",
        sa.Column("org_id", sa.String(length=64), nullable=False, server_default="vermithor"),
    )
    op.create_index("ix_investigations_org_id", "investigations", ["org_id"])

    # 2. Add org_id to repairs
    op.add_column(
        "repairs",
        sa.Column("org_id", sa.String(length=64), nullable=False, server_default="vermithor"),
    )
    op.create_index("ix_repairs_org_id", "repairs", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_repairs_org_id", table_name="repairs")
    op.drop_column("repairs", "org_id")

    op.drop_index("ix_investigations_org_id", table_name="investigations")
    op.drop_column("investigations", "org_id")
