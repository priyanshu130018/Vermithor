"""Root conftest.py — re-exports shared fixtures so they are available to all test files."""
from backend.tests.conftest import (  # noqa: F401
    setup_clean_tables,
    db_session_fixture,
    client_fixture,
)
