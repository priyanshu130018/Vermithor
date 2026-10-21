import os
import shutil
import tempfile
from pathlib import Path
import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic import command


def test_alembic_ini_exists():
    """Verify alembic.ini is present in both root and backend context."""
    root_ini = Path("alembic.ini")
    backend_ini = Path("backend/alembic.ini")

    assert root_ini.exists(), "Root alembic.ini must exist for local workflows"
    assert backend_ini.exists(), "backend/alembic.ini must exist for Docker build context"


def test_migration_discovery():
    """Verify that migration scripts are discoverable by Alembic."""
    cfg = Config("backend/alembic.ini")
    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()

    assert len(heads) == 1, f"Expected exactly 1 migration head, got {heads}"
    assert heads[0] in (
        "001_initial_schema",
        "002_add_key_sequences",
        "003_add_investigations",
        "004_add_repairs",
        "005_add_repository_connections",
        "006_add_investigation_feedback",
        "007_add_pilot_onboarding_and_governance",
        "008_add_org_id_to_investigations_and_repairs",
    )


def test_migration_upgrade_and_idempotency():
    """Verify migration executes on a clean database and second run is a no-op."""
    temp_dir = tempfile.mkdtemp()
    try:
        db_path = os.path.join(temp_dir, "test_mig.db").replace("\\", "/")
        db_url = f"sqlite:///{db_path}"

        cfg = Config("backend/alembic.ini")
        cfg.set_main_option("sqlalchemy.url", db_url)

        # First run: applies schema
        command.upgrade(cfg, "head")

        # Second run: idempotent no-op
        command.upgrade(cfg, "head")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
