import logging
from typing import Any, Dict, Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import QueuePool, StaticPool

from backend.app.common.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class Base(DeclarativeBase):
    """Common Base class for all Vermithor domain models in the modular monolith."""
    pass


# Check if we are running in an automated SQLite test mode
if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    engine = create_engine(
        settings.DATABASE_URL,
        poolclass=QueuePool,
        pool_size=settings.DB_POOL_SIZE,
        max_overflow=settings.DB_MAX_OVERFLOW,
        pool_recycle=settings.DB_POOL_RECYCLE,
        pool_timeout=getattr(settings, "DB_POOL_TIMEOUT", 15),
        pool_pre_ping=True,
        echo=False,
    )

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency for obtaining a request-scoped database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_pool_status() -> Dict[str, Any]:
    """Safe connection pool diagnostic returning non-sensitive capacity metrics."""
    pool = engine.pool
    pool_class = pool.__class__.__name__
    if hasattr(pool, "size"):
        return {
            "pool_class": pool_class,
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "timeout_seconds": getattr(settings, "DB_POOL_TIMEOUT", 15),
        }
    return {
        "pool_class": pool_class,
        "mode": "static_or_unpooled",
    }
