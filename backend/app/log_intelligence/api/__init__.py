"""API package for Log Intelligence Service."""
from .logs import router as logs_router

__all__ = ["logs_router"]
