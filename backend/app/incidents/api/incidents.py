import math
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from backend.app.common.database import get_db
from backend.app.incidents.schemas.incident import (
    IncidentCreate,
    IncidentEventCreate,
    IncidentEventResponse,
    IncidentListResponse,
    IncidentResponse,
    IncidentSeverity,
    IncidentStatus,
)
from backend.app.incidents.services.incident_service import IncidentService, InvalidTransitionError

router = APIRouter(prefix="/incidents", tags=["incidents"])


@router.post(
    "",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an incident",
    description="Declare and persist a new operational incident in DETECTED state with an auto-generated incident key.",
)
def create_incident(
    incident_in: IncidentCreate,
    response: Response,
    db: Session = Depends(get_db),
) -> IncidentResponse:
    """Create a new incident."""
    if incident_in.incident_key and IncidentService.get_incident_by_key(db, incident_in.incident_key):
        response.status_code = status.HTTP_200_OK
    incident = IncidentService.create_incident(db, incident_in)
    return IncidentResponse.from_orm_model(incident)


@router.get(
    "/{incident_key}",
    response_model=IncidentResponse,
    summary="Get incident by incident_key",
    description="Retrieve full details for an incident by its human-facing key (e.g. INC-000001).",
)
def get_incident(
    incident_key: str,
    db: Session = Depends(get_db),
) -> IncidentResponse:
    """Retrieve an incident by key."""
    incident = IncidentService.get_incident_by_key(db, incident_key)
    if not incident:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with key '{incident_key}' not found",
        )
    return IncidentResponse.from_orm_model(incident)


@router.get(
    "",
    response_model=IncidentListResponse,
    summary="List incidents with filtering and pagination",
    description="Retrieve a paginated list of operational incidents ordered by creation time descending.",
)
def list_incidents(
    page: int = Query(1, ge=1, description="Page number starting from 1"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    status_filter: Optional[IncidentStatus] = Query(None, alias="status", description="Filter by status"),
    severity: Optional[IncidentSeverity] = Query(None, description="Filter by severity"),
    environment: Optional[str] = Query(None, description="Filter by environment"),
    db: Session = Depends(get_db),
) -> IncidentListResponse:
    """List incidents with filtering and pagination."""
    items, total = IncidentService.list_incidents(
        db=db,
        page=page,
        page_size=page_size,
        status=status_filter.value if status_filter else None,
        severity=severity.value if severity else None,
        environment=environment,
    )
    total_pages = math.ceil(total / page_size) if total > 0 else 0

    return IncidentListResponse(
        items=[IncidentResponse.from_orm_model(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


# Lifecycle state transition endpoints

def _apply_transition(
    incident_key: str,
    target_status: IncidentStatus,
    db: Session,
) -> IncidentResponse:
    """Helper to execute state transitions and map exceptions to HTTP status codes."""
    try:
        updated = IncidentService.transition_status(db, incident_key, target_status)
        return IncidentResponse.from_orm_model(updated)
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with key '{incident_key}' not found",
        )
    except InvalidTransitionError as err:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(err),
        )


@router.post(
    "/{incident_key}/investigate",
    response_model=IncidentResponse,
    summary="Transition incident to INVESTIGATING",
    description="Mark an incident as actively being investigated.",
)
def investigate_incident(
    incident_key: str,
    db: Session = Depends(get_db),
) -> IncidentResponse:
    return _apply_transition(incident_key, IncidentStatus.INVESTIGATING, db)


@router.post(
    "/{incident_key}/acknowledge",
    response_model=IncidentResponse,
    summary="Transition incident to ACKNOWLEDGED",
    description="Acknowledge ownership and awareness of an operational incident.",
)
def acknowledge_incident(
    incident_key: str,
    db: Session = Depends(get_db),
) -> IncidentResponse:
    return _apply_transition(incident_key, IncidentStatus.ACKNOWLEDGED, db)


@router.post(
    "/{incident_key}/resolve",
    response_model=IncidentResponse,
    summary="Transition incident to RESOLVED",
    description="Mark incident as mitigated and resolved, setting ended_at timestamp.",
)
def resolve_incident(
    incident_key: str,
    db: Session = Depends(get_db),
) -> IncidentResponse:
    return _apply_transition(incident_key, IncidentStatus.RESOLVED, db)


@router.post(
    "/{incident_key}/close",
    response_model=IncidentResponse,
    summary="Transition incident to CLOSED",
    description="Close an incident following post-mortem or retrospective.",
)
def close_incident(
    incident_key: str,
    db: Session = Depends(get_db),
) -> IncidentResponse:
    return _apply_transition(incident_key, IncidentStatus.CLOSED, db)


@router.post(
    "/{incident_key}/false-positive",
    response_model=IncidentResponse,
    summary="Transition incident to FALSE_POSITIVE",
    description="Dismiss incident as a non-actionable alert or false positive.",
)
def false_positive_incident(
    incident_key: str,
    db: Session = Depends(get_db),
) -> IncidentResponse:
    return _apply_transition(incident_key, IncidentStatus.FALSE_POSITIVE, db)


# Incident Evidence / Event Association Endpoints

@router.post(
    "/{incident_key}/events",
    response_model=IncidentEventResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Associate an event with an incident",
    description="Attach an observability signal (by canonical event_id) to an incident with a relation type and correlation score.",
)
def add_event_to_incident(
    incident_key: str,
    event_in: IncidentEventCreate,
    response: Response,
    db: Session = Depends(get_db),
) -> IncidentEventResponse:
    """Associate an external event with an incident."""
    assoc, is_new = IncidentService.add_event_to_incident(db, incident_key, event_in)
    if assoc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with key '{incident_key}' not found",
        )
    if not is_new:
        response.status_code = status.HTTP_200_OK
    return IncidentEventResponse.from_orm_model(assoc)


@router.get(
    "/{incident_key}/events",
    response_model=List[IncidentEventResponse],
    summary="Get associated events for an incident",
    description="Retrieve all external canonical event associations attached to this incident.",
)
def get_incident_events(
    incident_key: str,
    db: Session = Depends(get_db),
) -> List[IncidentEventResponse]:
    """List associated events for an incident."""
    events = IncidentService.get_incident_events(db, incident_key)
    if events is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident with key '{incident_key}' not found",
        )
    return [IncidentEventResponse.from_orm_model(ev) for ev in events]
