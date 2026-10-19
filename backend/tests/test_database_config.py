import logging
import os
from unittest.mock import patch, MagicMock
import pytest
from sqlalchemy.engine import make_url

from backend.app.common.config import Settings, normalize_database_url, get_safe_db_diagnostic
from backend.alembic.env import get_url as alembic_get_url, log_safe_url_diagnostic


def test_normalize_database_url_various_schemes():
    # Standard postgresql:// -> postgresql+psycopg://
    url1 = "postgresql://neondb_owner:npg_secret@ep-curly-mode-b4ilila7.c-6.us-east-2.aws.neon.tech/neondb?sslmode=require"
    norm1 = normalize_database_url(url1)
    assert norm1.startswith("postgresql+psycopg://")
    parsed1 = make_url(norm1)
    assert parsed1.drivername == "postgresql+psycopg"
    assert parsed1.query["sslmode"] == "require"
    assert parsed1.host == "ep-curly-mode-b4ilila7.c-6.us-east-2.aws.neon.tech"

    # Legacy postgres:// -> postgresql+psycopg:// with channel_binding
    url2 = "postgres://neondb_owner:npg_secret@ep-curly-mode-b4ilila7.c-6.us-east-2.aws.neon.tech/neondb?channel_binding=require&sslmode=require"
    norm2 = normalize_database_url(url2)
    assert norm2.startswith("postgresql+psycopg://")
    parsed2 = make_url(norm2)
    assert parsed2.drivername == "postgresql+psycopg"
    assert parsed2.query["sslmode"] == "require"
    assert parsed2.query["channel_binding"] == "require"

    # psycopg2 explicit -> postgresql+psycopg://
    url3 = "postgresql+psycopg2://user:pass@host:5432/db"
    norm3 = normalize_database_url(url3)
    assert norm3.startswith("postgresql+psycopg://")

    # Already postgresql+psycopg:// -> untouched
    url4 = "postgresql+psycopg://user:pass@host:5432/db?sslmode=require"
    norm4 = normalize_database_url(url4)
    assert norm4 == url4

    # Stripping outer quotes
    url5 = "\"postgresql://user:pass@host:5432/db?sslmode=require\""
    norm5 = normalize_database_url(url5)
    assert norm5 == "postgresql+psycopg://user:pass@host:5432/db?sslmode=require"

    # Non-postgres URL -> untouched
    url6 = "sqlite:///test.db"
    norm6 = normalize_database_url(url6)
    assert norm6 == "sqlite:///test.db"

    # None and empty
    assert normalize_database_url(None) is None
    assert normalize_database_url("") == ""


def test_settings_normalizes_database_url():
    # When DATABASE_URL is provided with postgresql://
    settings = Settings(
        DATABASE_URL="postgresql://user:secret@ep-pooler.neon.tech/neondb?sslmode=require",
        DATABASE_URL_UNPOOLED="postgres://user:secret@ep-direct.neon.tech/neondb?sslmode=require",
    )
    assert settings.DATABASE_URL.startswith("postgresql+psycopg://")
    assert settings.DATABASE_URL_UNPOOLED.startswith("postgresql+psycopg://")
    assert "sslmode=require" in settings.DATABASE_URL
    assert "sslmode=require" in settings.DATABASE_URL_UNPOOLED


def test_settings_fallback_database_url():
    # When DATABASE_URL is not provided or None, defaults to Neon database URL
    settings = Settings(DATABASE_URL=None)
    assert settings.DATABASE_URL.startswith("postgresql+psycopg://")
    assert "neon.tech" in settings.DATABASE_URL


def test_alembic_get_url_resolution_env_unpooled_precedence():
    # DATABASE_URL_UNPOOLED in os.environ has highest precedence among env vars
    env_vars = {
        "DATABASE_URL_UNPOOLED": "postgresql://user:pass@ep-unpooled.c-6.neon.tech/neondb?sslmode=require",
        "DATABASE_URL": "postgresql://user:pass@ep-pooled.c-6.neon.tech/neondb?sslmode=require",
    }
    with patch.dict(os.environ, env_vars, clear=True):
        url = alembic_get_url()
        assert url.startswith("postgresql+psycopg://")
        assert "ep-unpooled.c-6.neon.tech" in url


def test_alembic_get_url_resolution_settings_unpooled_precedence():
    # When os.environ has no unpooled URL, settings.DATABASE_URL_UNPOOLED is preferred over pooled settings
    with patch.dict(os.environ, {}, clear=True):
        mock_settings = MagicMock()
        mock_settings.DATABASE_URL_UNPOOLED = "postgresql://user:pass@ep-direct-settings.neon.tech/neondb?sslmode=require"
        mock_settings.DATABASE_URL = "postgresql://user:pass@ep-pooled-settings-pooler.neon.tech/neondb?sslmode=require"

        with patch("backend.alembic.env.get_settings", return_value=mock_settings):
            url = alembic_get_url()
            assert url.startswith("postgresql+psycopg://")
            assert "ep-direct-settings.neon.tech" in url


def test_alembic_get_url_resolution_env_database_url_fallback():
    # When no unpooled URL is present anywhere, fallback to DATABASE_URL in os.environ
    env_vars = {
        "DATABASE_URL": "postgresql://user:pass@ep-fallback-env.neon.tech/neondb?sslmode=require",
    }
    with patch.dict(os.environ, env_vars, clear=True):
        mock_settings = MagicMock()
        mock_settings.DATABASE_URL_UNPOOLED = None
        mock_settings.DATABASE_URL = "postgresql://user:pass@ep-fallback-settings.neon.tech/neondb?sslmode=require"

        with patch("backend.alembic.env.get_settings", return_value=mock_settings):
            url = alembic_get_url()
            assert url.startswith("postgresql+psycopg://")
            assert "ep-fallback-env.neon.tech" in url


def test_alembic_pooled_url_warning(caplog):
    # When a pooled URL is selected, a warning is logged
    env_vars = {
        "DATABASE_URL": "postgresql://user:pass@ep-my-db-pooler.c-6.neon.tech/neondb?sslmode=require",
    }
    with patch.dict(os.environ, env_vars, clear=True):
        mock_settings = MagicMock()
        mock_settings.DATABASE_URL_UNPOOLED = None

        with patch("backend.alembic.env.get_settings", return_value=mock_settings):
            with caplog.at_level(logging.WARNING, logger="alembic.env"):
                url = alembic_get_url()
                assert "ep-my-db-pooler.c-6.neon.tech" in url
                assert any("pooled database connection" in record.message for record in caplog.records)


def test_get_safe_db_diagnostic():
    # Test pooled URL by -pooler suffix
    pooled_url = "postgresql://neondb_owner:super_secret_pw@ep-curly-mode-b4ilila7-pooler.c-6.us-east-2.aws.neon.tech/neondb?channel_binding=require&sslmode=require"
    diag1 = get_safe_db_diagnostic(pooled_url)
    assert diag1["hostname"] == "ep-curly-mode-b4ilila7-pooler.c-6.us-east-2.aws.neon.tech"
    assert diag1["username"] == "neondb_owner"
    assert diag1["database"] == "neondb"
    assert diag1["mode"] == "pooled"
    assert diag1["password_present"] is True
    # Ensure sensitive items are never in keys, values, or string representations
    assert "password" not in diag1
    assert "super_secret_pw" not in str(diag1)
    assert "sslmode" not in str(diag1)
    assert "channel_binding" not in str(diag1)

    # Test pooled URL by port 6543 (PgBouncer standard port)
    pooled_port_url = "postgresql://neondb_owner:secret@db.example.com:6543/neondb"
    diag_port = get_safe_db_diagnostic(pooled_port_url)
    assert diag_port["mode"] == "pooled"
    assert diag_port["hostname"] == "db.example.com"
    assert "secret" not in str(diag_port)

    # Test unpooled URL
    unpooled_url = "postgresql+psycopg://neondb_owner:another_secret@ep-curly-mode-b4ilila7.c-6.us-east-2.aws.neon.tech/neondb?sslmode=require"
    diag2 = get_safe_db_diagnostic(unpooled_url)
    assert diag2["hostname"] == "ep-curly-mode-b4ilila7.c-6.us-east-2.aws.neon.tech"
    assert diag2["username"] == "neondb_owner"
    assert diag2["database"] == "neondb"
    assert diag2["mode"] == "unpooled"
    assert diag2["password_present"] is True
    assert "another_secret" not in str(diag2)

    # Test URL without password
    no_pass_url = "postgresql://readonly_user@localhost:5432/testdb"
    diag_no_pass = get_safe_db_diagnostic(no_pass_url)
    assert diag_no_pass["hostname"] == "localhost"
    assert diag_no_pass["username"] == "readonly_user"
    assert diag_no_pass["database"] == "testdb"
    assert diag_no_pass["password_present"] is False
    assert diag_no_pass["mode"] == "unpooled"

    # Test None and empty
    diag_none = get_safe_db_diagnostic(None)
    assert diag_none["hostname"] is None
    assert diag_none["password_present"] is False
    assert diag_none["mode"] == "unknown"

    diag_empty = get_safe_db_diagnostic("")
    assert diag_empty["hostname"] is None
    assert diag_empty["password_present"] is False
    assert diag_empty["mode"] == "unknown"

    # Test malformed URL
    diag_bad = get_safe_db_diagnostic("not_a_valid_url://:::invalid")
    assert diag_bad["hostname"] == "unparseable"
    assert diag_bad["password_present"] is False


def test_log_safe_url_diagnostic(caplog):
    test_url = "postgresql://user:super_secret_pw@ep-direct.neon.tech/neondb?sslmode=require"
    with caplog.at_level(logging.INFO, logger="alembic.env"):
        log_safe_url_diagnostic(test_url, source="test_source")
        assert len(caplog.records) >= 1
        record = caplog.records[-1]
        assert "ep-direct.neon.tech" in record.message
        assert "super_secret_pw" not in record.message
        assert "sslmode" not in record.message
        assert "test_source" in record.message
