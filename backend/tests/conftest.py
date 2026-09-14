import os
from pathlib import Path
from typing import Generator
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import backend.app.common.database as common_db
from backend.app.common.database import Base, get_db

# Import all models to ensure complete metadata registration
import backend.app.ingestion.db.models
import backend.app.incidents.db.models
import backend.app.anomaly.db.models
import backend.app.correlation.db.models
import backend.app.rca.db.models
import backend.app.log_intelligence.db.models
import backend.app.retrieval.db.models
import backend.app.summary.db.models

from backend.app.main import app

# Shared file-based SQLite database for robust multi-session test execution
TEST_DB_FILE = Path(__file__).parent / "test_vermithor.db"
SQLALCHEMY_TEST_DATABASE_URL = f"sqlite:///{TEST_DB_FILE.resolve().as_posix()}"

test_engine = create_engine(
    SQLALCHEMY_TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
)

# Bind global SessionLocal and engine to test_engine for all unit test executions
common_db.SessionLocal = TestingSessionLocal
common_db.engine = test_engine


@pytest.fixture(autouse=True)
def setup_clean_tables():
    """Create fresh tables before each test."""
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield


@pytest.fixture(name="db_session")
def db_session_fixture() -> Generator[Session, None, None]:
    """Provide an isolated clean database session per test."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(name="client")
def client_fixture() -> Generator[TestClient, None, None]:
    """TestClient fixture with overridden get_db dependency pointing to test SQLite."""
    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
