import math
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.common.database import get_db
from backend.app.ingestion.schemas.event import (
    EventCreate,
    EventListResponse,
    EventResponse,
    EventType,
    Severity,
)
from backend.app.ingestion.services.event_service import EventService

router = APIRouter(prefix="/events", tags=["events"])


@router.post(
    "",
    response_model=EventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest an observability event",
    description="Ingests, validates, normalizes, and persists an observability event. Repeated submissions with the same event_id are idempotent.",
    responses={
        201: {"description": "Event successfully created"},
        200: {"description": "Event already exists (idempotent duplicate)"},
        422: {"description": "Validation error"},
    },
)
def create_event(
    event_in: EventCreate,
    response: Response,
    db: Session = Depends(get_db),
) -> EventResponse:
    """Ingest an observability event with idempotent duplicate handling."""
    event, is_created = EventService.create_event(db, event_in)
    if not is_created:
        response.status_code = status.HTTP_200_OK
    return EventResponse.from_orm_model(event)


@router.get(
    "/{event_id}",
    response_model=EventResponse,
    summary="Get event by event_id",
    description="Retrieve a single event by its unique client/system event identifier.",
    responses={
        200: {"description": "Event details"},
        404: {"description": "Event not found"},
    },
)
def get_event(
    event_id: str,
    db: Session = Depends(get_db),
) -> EventResponse:
    """Retrieve an event by event_id."""
    event = EventService.get_event_by_event_id(db, event_id)
    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Event with event_id '{event_id}' not found",
        )
    return EventResponse.from_orm_model(event)


@router.get(
    "",
    response_model=EventListResponse,
    summary="List events with filtering and pagination",
    description="Retrieve a paginated list of observability events with optional filtering by service, environment, event_type, and severity.",
)
def list_events(
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    service: Optional[str] = Query(None, description="Filter by service name"),
    environment: Optional[str] = Query(None, description="Filter by environment"),
    event_type: Optional[EventType] = Query(None, description="Filter by event type"),
    severity: Optional[Severity] = Query(None, description="Filter by severity"),
    db: Session = Depends(get_db),
) -> EventListResponse:
    """List events with pagination and filtering."""
    items, total = EventService.list_events(
        db=db,
        page=page,
        page_size=page_size,
        service=service,
        environment=environment,
        event_type=event_type.value if event_type else None,
        severity=severity.value if severity else None,
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return EventListResponse(
        items=[EventResponse.from_orm_model(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )
