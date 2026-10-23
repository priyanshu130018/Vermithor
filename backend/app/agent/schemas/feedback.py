import uuid
from datetime import datetime
from enum import Enum
from typing import Optional
from pydantic import BaseModel, ConfigDict, Field


class FeedbackStatus(str, Enum):
    """Operator verification status of an investigation."""
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    UNRESOLVED = "UNRESOLVED"


class InvestigationFeedbackCreate(BaseModel):
    """Payload to record operator verification feedback on an investigation."""
    feedback_status: FeedbackStatus = Field(..., description="Operator assessment: CONFIRMED, REJECTED, or UNRESOLVED")
    confirmed_root_cause: Optional[str] = Field(None, max_length=255, description="Confirmed root cause if different or verified")
    evidence_reference: Optional[str] = Field(None, description="Supporting log, metric, or PR link")
    explanation: Optional[str] = Field(None, description="Operator narrative explanation")


class InvestigationFeedbackResponse(BaseModel):
    """API response model for operator verification feedback."""
    id: uuid.UUID
    investigation_key: str
    incident_key: str
    org_id: str
    feedback_status: FeedbackStatus
    operator_id: str
    confirmed_root_cause: Optional[str] = None
    evidence_reference: Optional[str] = None
    explanation: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
