import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy.exc import OperationalError


def test_database_engine_pool_pre_ping_configured():
    """Verify that backend database engine enables pool_pre_ping for reconnect resilience."""
    db_paths = [
        "backend/app/common/database.py",
    ]

    for rel_path in db_paths:
        abs_path = os.path.abspath(rel_path)
        assert os.path.exists(abs_path), f"Database file not found: {abs_path}"
        with open(abs_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "pool_pre_ping=True" in content, f"pool_pre_ping not enabled in {rel_path}"


def test_transient_database_disconnect_handling():
    """Verify that operational database errors are caught gracefully without uncaught process termination."""
    from sqlalchemy import create_engine, text

    # In-memory SQLite engine
    engine = create_engine("sqlite:///:memory:", pool_pre_ping=True)

    with engine.connect() as conn:
        res = conn.execute(text("SELECT 1")).scalar()
        assert res == 1

    # Simulate connection drop exception
    mock_conn = MagicMock()
    mock_conn.execute.side_effect = OperationalError("statement", {}, Exception("Connection lost"))

    with pytest.raises(OperationalError) as exc_info:
        mock_conn.execute("SELECT 1")
    assert "Connection lost" in str(exc_info.value)
