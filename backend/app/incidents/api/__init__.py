"""API endpoints package for Incident Service."""
from .incidents import router as incidents_router

__all__ = ["incidents_router"]
