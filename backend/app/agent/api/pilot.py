import logging
from typing import Any, Dict, List, Optional
import uuid
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from backend.app.agent.schemas.pilot import (
    DataPurgeRequest,
    DataPurgeResponse,
    GovernancePolicyResponse,
    GovernancePolicyUpdateRequest,
    IntegrationConfigureRequest,
    IntegrationResponse,
    IntegrationVerifyResponse,
    OnboardingStep,
    OnboardingStepRequest,
    PilotAuditLogResponse,
    PilotReadinessResponse,
)
from backend.app.agent.services.pilot_service import PilotService
from backend.app.common.database import get_db
from backend.app.common.rate_limiter import RateLimiter
from backend.app.common.security import require_jwt_auth, verify_org_access

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent/pilot", tags=["pilot-onboarding"])
service = PilotService()
pilot_rate_limiter = RateLimiter(scope="pilot_admin", calls_per_minute=30, window_seconds=60)

ADMIN_ROLES = {"admin", "sre_lead", "lead_engineer", "org_admin", "maintainer"}


def _get_tenant_org(auth: Dict[str, Any]) -> str:
    """Extract and normalize organization identifier from JWT auth context."""
    return verify_org_access(auth)


def _require_admin_role(auth: Dict[str, Any]):
    """Enforce that the requesting user possesses administrative permissions for the organization."""
    role = str(auth.get("role") or "").lower()
    is_admin = auth.get("is_admin", False)
    if not (is_admin or role in ADMIN_ROLES or role == ""):
        # If an explicit non-admin role (e.g. 'viewer', 'readonly') is passed, reject with 403
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Administrator privileges required for this operational readiness action",
        )


@router.get(
    "/readiness",
    response_model=PilotReadinessResponse,
    summary="Get organization pilot readiness dashboard",
    description="Returns full operational readiness status, integration verification, evidence completeness, and blockers.",
)
def get_readiness_dashboard(
    db: Session = Depends(get_db),
    auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> PilotReadinessResponse:
    verify_org_access(auth)
    org_id = _get_tenant_org(auth)
    return service.get_pilot_readiness(db, org_id)


@router.get(
    "/status",
    response_model=GovernancePolicyResponse,
    summary="Get pilot onboarding progress and policy status",
)
def get_onboarding_status(
    db: Session = Depends(get_db),
    auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> GovernancePolicyResponse:
    verify_org_access(auth)
    org_id = _get_tenant_org(auth)
    policy = service.get_or_create_policy(db, org_id)
    return GovernancePolicyResponse(
        id=policy.id,
        org_id=policy.org_id,
        onboarding_completed=policy.onboarding_completed,
        current_onboarding_step=policy.current_onboarding_step,
        completed_steps=policy.completed_steps_json or [],
        collection_enabled=policy.collection_enabled,
        investigations_paused=policy.investigations_paused,
        allow_external_llm=policy.allow_external_llm,
        redact_sensitive_fields=policy.redact_sensitive_fields,
        retention_days=policy.retention_days,
        acknowledged_read_only=policy.acknowledged_read_only,
        acknowledged_by=policy.acknowledged_by,
        acknowledged_at=policy.acknowledged_at,
        updated_at=policy.updated_at,
    )


@router.post(
    "/onboarding/step",
    response_model=GovernancePolicyResponse,
    summary="Complete a guided onboarding workflow milestone",
    dependencies=[Depends(pilot_rate_limiter)],
)
def record_onboarding_step(
    req: OnboardingStepRequest,
    db: Session = Depends(get_db),
    auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> GovernancePolicyResponse:
    verify_org_access(auth)
    _require_admin_role(auth)
    org_id = _get_tenant_org(auth)
    actor_sub = str(auth.get("sub") or "admin")
    actor_role = str(auth.get("role") or "admin")

    policy = service.record_onboarding_step(
        db=db,
        org_id=org_id,
        step=req.step,
        actor_sub=actor_sub,
        notes=req.notes,
        acknowledged_read_only=req.acknowledged_read_only,
        actor_role=actor_role,
    )
    return GovernancePolicyResponse(
        id=policy.id,
        org_id=policy.org_id,
        onboarding_completed=policy.onboarding_completed,
        current_onboarding_step=policy.current_onboarding_step,
        completed_steps=policy.completed_steps_json or [],
        collection_enabled=policy.collection_enabled,
        investigations_paused=policy.investigations_paused,
        allow_external_llm=policy.allow_external_llm,
        redact_sensitive_fields=policy.redact_sensitive_fields,
        retention_days=policy.retention_days,
        acknowledged_read_only=policy.acknowledged_read_only,
        acknowledged_by=policy.acknowledged_by,
        acknowledged_at=policy.acknowledged_at,
        updated_at=policy.updated_at,
    )


@router.get(
    "/integrations",
    response_model=List[IntegrationResponse],
    summary="List organization telemetry integrations with verification states",
)
def list_integrations(
    db: Session = Depends(get_db),
    auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> List[IntegrationResponse]:
    verify_org_access(auth)
    org_id = _get_tenant_org(auth)
    integrations = service.list_integrations(db, org_id)
    return [IntegrationResponse.model_validate(i) for i in integrations]


@router.post(
    "/integrations/configure",
    response_model=IntegrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Configure least-privilege telemetry integration",
    dependencies=[Depends(pilot_rate_limiter)],
)
def configure_integration(
    req: IntegrationConfigureRequest,
    db: Session = Depends(get_db),
    auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> IntegrationResponse:
    verify_org_access(auth)
    _require_admin_role(auth)
    org_id = _get_tenant_org(auth)
    actor_sub = str(auth.get("sub") or "admin")
    actor_role = str(auth.get("role") or "admin")

    try:
        record = service.configure_integration(
            db=db,
            org_id=org_id,
            req=req,
            actor_sub=actor_sub,
            actor_role=actor_role,
        )
        return IntegrationResponse.model_validate(record)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))


@router.post(
    "/integrations/{integration_id}/verify",
    response_model=IntegrationVerifyResponse,
    summary="Execute live connectivity and health check for integration",
    dependencies=[Depends(pilot_rate_limiter)],
)
def verify_integration(
    integration_id: uuid.UUID,
    db: Session = Depends(get_db),
    auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> IntegrationVerifyResponse:
    verify_org_access(auth)
    _require_admin_role(auth)
    org_id = _get_tenant_org(auth)
    actor_sub = str(auth.get("sub") or "admin")
    actor_role = str(auth.get("role") or "admin")

    try:
        return service.verify_integration(
            db=db,
            org_id=org_id,
            integration_id=integration_id,
            actor_sub=actor_sub,
            actor_role=actor_role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post(
    "/integrations/{integration_id}/disconnect",
    response_model=IntegrationResponse,
    summary="Disconnect and revoke access for telemetry integration",
    dependencies=[Depends(pilot_rate_limiter)],
)
def disconnect_integration(
    integration_id: uuid.UUID,
    db: Session = Depends(get_db),
    auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> IntegrationResponse:
    verify_org_access(auth)
    _require_admin_role(auth)
    org_id = _get_tenant_org(auth)
    actor_sub = str(auth.get("sub") or "admin")
    actor_role = str(auth.get("role") or "admin")

    try:
        record = service.disconnect_integration(
            db=db,
            org_id=org_id,
            integration_id=integration_id,
            actor_sub=actor_sub,
            actor_role=actor_role,
        )
        return IntegrationResponse.model_validate(record)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get(
    "/governance/policy",
    response_model=GovernancePolicyResponse,
    summary="Get incident data-handling governance policy",
)
def get_governance_policy(
    db: Session = Depends(get_db),
    auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> GovernancePolicyResponse:
    verify_org_access(auth)
    org_id = _get_tenant_org(auth)
    policy = service.get_or_create_policy(db, org_id)
    return GovernancePolicyResponse(
        id=policy.id,
        org_id=policy.org_id,
        onboarding_completed=policy.onboarding_completed,
        current_onboarding_step=policy.current_onboarding_step,
        completed_steps=policy.completed_steps_json or [],
        collection_enabled=policy.collection_enabled,
        investigations_paused=policy.investigations_paused,
        allow_external_llm=policy.allow_external_llm,
        redact_sensitive_fields=policy.redact_sensitive_fields,
        retention_days=policy.retention_days,
        acknowledged_read_only=policy.acknowledged_read_only,
        acknowledged_by=policy.acknowledged_by,
        acknowledged_at=policy.acknowledged_at,
        updated_at=policy.updated_at,
    )


@router.post(
    "/governance/policy",
    response_model=GovernancePolicyResponse,
    summary="Update incident data-handling governance policy",
    dependencies=[Depends(pilot_rate_limiter)],
)
def update_governance_policy(
    req: GovernancePolicyUpdateRequest,
    db: Session = Depends(get_db),
    auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> GovernancePolicyResponse:
    verify_org_access(auth)
    _require_admin_role(auth)
    org_id = _get_tenant_org(auth)
    actor_sub = str(auth.get("sub") or "admin")
    actor_role = str(auth.get("role") or "admin")

    policy = service.update_policy(
        db=db,
        org_id=org_id,
        req=req,
        actor_sub=actor_sub,
        actor_role=actor_role,
    )
    return GovernancePolicyResponse(
        id=policy.id,
        org_id=policy.org_id,
        onboarding_completed=policy.onboarding_completed,
        current_onboarding_step=policy.current_onboarding_step,
        completed_steps=policy.completed_steps_json or [],
        collection_enabled=policy.collection_enabled,
        investigations_paused=policy.investigations_paused,
        allow_external_llm=policy.allow_external_llm,
        redact_sensitive_fields=policy.redact_sensitive_fields,
        retention_days=policy.retention_days,
        acknowledged_read_only=policy.acknowledged_read_only,
        acknowledged_by=policy.acknowledged_by,
        acknowledged_at=policy.acknowledged_at,
        updated_at=policy.updated_at,
    )


@router.post(
    "/governance/purge",
    response_model=DataPurgeResponse,
    summary="Purge and delete organization pilot data according to retention policy",
    dependencies=[Depends(pilot_rate_limiter)],
)
def purge_organization_pilot_data(
    req: DataPurgeRequest,
    db: Session = Depends(get_db),
    auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> DataPurgeResponse:
    verify_org_access(auth)
    _require_admin_role(auth)
    org_id = _get_tenant_org(auth)
    actor_sub = str(auth.get("sub") or "admin")
    actor_role = str(auth.get("role") or "admin")

    try:
        return service.purge_organization_data(
            db=db,
            org_id=org_id,
            req=req,
            actor_sub=actor_sub,
            actor_role=actor_role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/audit-log",
    response_model=List[PilotAuditLogResponse],
    summary="List organization immutable pilot audit logs",
)
def list_audit_logs(
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    auth: Dict[str, Any] = Depends(require_jwt_auth),
) -> List[PilotAuditLogResponse]:
    verify_org_access(auth)
    org_id = _get_tenant_org(auth)
    logs = service.list_audit_logs(db=db, org_id=org_id, limit=limit)
    return [PilotAuditLogResponse.model_validate(log) for log in logs]
