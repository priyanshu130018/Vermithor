from backend.app.log_intelligence.parsing.classifier import LogClassifier
from backend.app.log_intelligence.schemas.logs import LogCategory


def test_classifier_domains():
    """Verify deterministic categorization across key operational domains."""
    assert LogClassifier.classify("Connection refused to postgres db", "booking-api") == LogCategory.DATABASE
    assert LogClassifier.classify("Deadlock detected on table orders", "booking-api") == LogCategory.DATABASE
    assert LogClassifier.classify("User authentication failed: token expired", "auth-api") == LogCategory.AUTHENTICATION
    assert LogClassifier.classify("Out of memory OOM killer killed process", "worker-api") == LogCategory.RESOURCE
    assert LogClassifier.classify("HTTP 500 Internal Server Error", "gateway-api") == LogCategory.HTTP
    assert LogClassifier.classify("Deployment release v2.1.0 completed", "deploy-service") == LogCategory.DEPLOYMENT
    assert LogClassifier.classify("Redis cluster down connection failed", "cache-service") == LogCategory.CACHE
    assert LogClassifier.classify("DNS lookup failed: socket timeout", "payment-api") == LogCategory.NETWORK
