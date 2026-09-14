"""API endpoints module for Ingestion Service."""
from .events import router as events_router

__all__ = ["events_router"]
