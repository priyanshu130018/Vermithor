import os
from pathlib import Path
from typing import Generator
import pytest

os.environ["EMBEDDING_PROVIDER"] = "mock"
from backend.app.log_intelligence.embedding.service import get_embedding_service
from backend.app.log_intelligence.embedding.mock_provider import MockEmbeddingProvider
get_embedding_service(provider=MockEmbeddingProvider())
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import backend.app.common.database as common_db
from backend.app.common.database import Base, get_db
from backend.app.common.security import create_access_token

# Import all models to ensure complete metadata registration
import backend.app.ingestion.db.models
import backend.app.incidents.db.models
import backend.app.anomaly.db.models
import backend.app.correlation.db.models
import backend.app.rca.db.models
import backend.app.log_intelligence.db.models
import backend.app.retrieval.db.models
import backend.app.summary.db.models
import backend.app.agent.db.models

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
    try:
        test_engine.dispose()
        Base.metadata.drop_all(bind=test_engine, checkfirst=True)
    except Exception:
        pass
    Base.metadata.create_all(bind=test_engine, checkfirst=True)
    yield
    try:
        test_engine.dispose()
    except Exception:
        pass
    test_engine.dispose()


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
    """TestClient fixture with overridden get_db and valid Bearer JWT header."""
    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    valid_token = create_access_token({"sub": "sre-test-suite-user", "org_id": "vermithor", "role": "sre_lead"})
    with TestClient(app, headers={"Authorization": f"Bearer {valid_token}"}) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture(name="unauthenticated_client")
def unauthenticated_client_fixture() -> Generator[TestClient, None, None]:
    """TestClient fixture without default authorization header for testing authentication boundaries."""
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
