import pytest
from pydantic import ValidationError
from backend.app.summary.schemas.summaries import IncidentSummaryGeneratedSchema


def test_schema_validation_valid():
    """Verify valid summary payload passes validation."""
    data = {
        "executive_summary": "Booking API failed due to database saturation.",
        "what_happened": "Database connection pool saturated at 12:02.",
        "probable_root_cause": "PostgreSQL Connection Pool Exhaustion",
        "impact": {
            "services": ["booking-api"],
            "severity": "CRITICAL",
            "description": "500 errors",
        },
        "timeline": [
            {"timestamp": "2026-08-29T12:02:00Z", "event": "DB Saturated", "source": "[LOG:evt-1]"}
        ],
        "evidence": [
            {"claim": "DB saturated", "source_type": "LOG", "source_id": "evt-1", "support": "Pool at 100%"}
        ],
        "remediation": [
            {"action": "Restart DB pool", "priority": "HIGH", "reason": "Clear connections"}
        ],
        "confidence": 0.89,
        "limitations": ["No CPU spike detected"],
    }
    schema = IncidentSummaryGeneratedSchema.model_validate(data)
    assert schema.confidence == 0.89
    assert schema.impact.severity == "CRITICAL"


def test_schema_validation_missing_required_fields():
    """Verify missing required fields raise ValidationError."""
    with pytest.raises(ValidationError):
        IncidentSummaryGeneratedSchema.model_validate({
            "what_happened": "Something broke",
        })


def test_schema_validation_invalid_confidence():
    """Verify confidence outside [0, 1] raises ValidationError."""
    with pytest.raises(ValidationError):
        IncidentSummaryGeneratedSchema.model_validate({
            "executive_summary": "Summary",
            "what_happened": "Narrative",
            "probable_root_cause": "Root cause",
            "confidence": 1.5,
        })
