import uuid
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, Field


class RunbookCreateRequest(BaseModel):
    """Payload for creating a new operational runbook."""
    runbook_key: Optional[str] = Field(None, min_length=3, max_length=64)
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    content: str = Field(..., min_length=1)
    service: Optional[str] = Field(None, max_length=128)
    environment: Optional[str] = Field(None, max_length=64)
    category: Optional[str] = Field(None, max_length=64)
    tags: List[str] = Field(default_factory=list)


class RunbookUpdateRequest(BaseModel):
    """Payload for updating an existing runbook."""
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    content: Optional[str] = Field(None, min_length=1)
    service: Optional[str] = None
    environment: Optional[str] = None
    category: Optional[str] = None
    tags: Optional[List[str]] = None


class RunbookResponse(BaseModel):
    """Operational runbook representation."""
    id: uuid.UUID
    runbook_key: str
    title: str
    description: Optional[str] = None
    content: str
    service: Optional[str] = None
    environment: Optional[str] = None
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RunbookListResponse(BaseModel):
    """Paginated list of runbooks."""
    items: List[RunbookResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class RunbookSearchRequest(BaseModel):
    """Runbook search query payload."""
    query: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=20)
    service: Optional[str] = None
    category: Optional[str] = None
