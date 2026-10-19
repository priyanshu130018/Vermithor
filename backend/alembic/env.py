import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Add project root directory to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

import logging

from backend.app.common.config import get_settings, normalize_database_url, get_safe_db_diagnostic
from backend.app.common.database import Base

# Import all domain models so SQLAlchemy Base knows about their metadata
import backend.app.anomaly.db.models  # noqa: F401
import backend.app.correlation.db.models  # noqa: F401
import backend.app.incidents.db.models  # noqa: F401
import backend.app.ingestion.db.models  # noqa: F401
import backend.app.log_intelligence.db.models  # noqa: F401
import backend.app.rca.db.models  # noqa: F401
import backend.app.retrieval.db.models  # noqa: F401
import backend.app.summary.db.models  # noqa: F401

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

config = getattr(context, "config", None)

if config and config.config_file_name:
    fileConfig(config.config_file_name)

logger = logging.getLogger("alembic.env")
target_metadata = Base.metadata


def log_safe_url_diagnostic(url: str, source: str) -> None:
    """Safely log connection parameters without exposing credentials or sensitive query params."""
    diag = get_safe_db_diagnostic(url)
    logger.info(
        "Migration DB connection target: source=%s, hostname=%s, username=%s, database=%s, mode=%s, password_present=%s",
        source,
        diag["hostname"],
        diag["username"],
        diag["database"],
        diag["mode"],
        diag["password_present"],
    )


def get_url() -> str:
    source = "settings.DATABASE_URL (fallback)"
    url = None

    if config:
        ini_url = config.get_main_option("sqlalchemy.url")
        if ini_url:
            source = "alembic.ini [sqlalchemy.url]"
            url = normalize_database_url(ini_url)

    # 1. Explicit direct unpooled connection from environment
    if not url and os.getenv("DATABASE_URL_UNPOOLED") and os.getenv("DATABASE_URL_UNPOOLED").strip():
        source = "os.environ['DATABASE_URL_UNPOOLED']"
        url = normalize_database_url(os.environ["DATABASE_URL_UNPOOLED"])

    # 2. Direct unpooled connection from settings (.env)
    if not url:
        settings = get_settings()
        if settings.DATABASE_URL_UNPOOLED and settings.DATABASE_URL_UNPOOLED.strip():
            source = "settings.DATABASE_URL_UNPOOLED"
            url = normalize_database_url(settings.DATABASE_URL_UNPOOLED)

    # 3. Environment DATABASE_URL (e.g. injected container URL)
    if not url and os.getenv("DATABASE_URL") and os.getenv("DATABASE_URL").strip():
        source = "os.environ['DATABASE_URL']"
        url = normalize_database_url(os.environ["DATABASE_URL"])

    # 4. Settings DATABASE_URL fallback
    if not url:
        settings = get_settings()
        if settings.DATABASE_URL and settings.DATABASE_URL.strip():
            source = "settings.DATABASE_URL"
            url = normalize_database_url(settings.DATABASE_URL)

    if not url:
        raise ValueError(
            "Could not determine database URL for Alembic migrations. "
            "Ensure DATABASE_URL_UNPOOLED or DATABASE_URL is configured."
        )

    diag = get_safe_db_diagnostic(url)
    if diag.get("mode") == "pooled":
        logger.warning(
            "Alembic migration is targeting a pooled database connection (hostname=%s). "
            "A direct, unpooled connection (DATABASE_URL_UNPOOLED) is strongly recommended for DDL migrations.",
            diag.get("hostname"),
        )

    log_safe_url_diagnostic(url, source)
    return url



def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if config is not None:
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()
