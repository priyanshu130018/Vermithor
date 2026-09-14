"""API package for Anomaly Detection Service."""
from .anomalies import router as anomalies_router
from .observations import router as observations_router

__all__ = ["anomalies_router", "observations_router"]
