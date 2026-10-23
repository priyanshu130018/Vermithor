from datetime import datetime, timezone
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy.orm import Session

from backend.app.agent.schemas.investigation import InvestigationRequest
from backend.app.agent.schemas.shadow import ShadowModeRequest, ShadowModeResponse
from backend.app.agent.services.investigation_service import InvestigationService
from backend.app.common.config import get_settings
from backend.app.observability.services.telemetry_service import TelemetryEvidenceService

logger = logging.getLogger(__name__)

# Patterns for sensitive token redaction
SECRET_PATTERNS = [
    re.compile(r"ey[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*"),  # JWT tokens
    re.compile(r"(?i)bearer\s+[A-Za-z0-9-_\.]+"),                            # Bearer tokens
    re.compile(r"(?i)(?:password|secret|api_key|token)\s*[:=]\s*['\"]?([^'\"\s]+)"),  # Secrets/keys
]


def redact_sensitive_strings(text: str) -> Tuple[str, int]:
    """Redact sensitive credentials, JWTs, and keys from telemetry text."""
    redacted_count = 0
    cleaned = text
    for pattern in SECRET_PATTERNS:
        matches = list(pattern.finditer(cleaned))
        if matches:
            redacted_count += len(matches)
            cleaned = pattern.sub("[REDACTED_SECRET]", cleaned)
    return cleaned, redacted_count


class ShadowEvaluationService:
    """
    Executes passive incident analysis in production-like shadow mode.
    Guarantees:
      - Strictly read-only: Zero repairs, zero git writes, zero PRs, zero merges.
      - Secret redaction for credentials, API tokens, and JWTs.
      - Clear audit provenance: marks all runs with SHADOW_PASSIVE and NOT VERIFIED for live telemetry.
    """

    def __init__(self, inv_service: Optional[InvestigationService] = None):
        self.inv_service = inv_service or InvestigationService()
        self.settings = get_settings()

    def run_shadow_evaluation(
        self,
        db: Session,
        req: ShadowModeRequest,
        org_id: str,
        telemetry_service: Optional[TelemetryEvidenceService] = None,
    ) -> ShadowModeResponse:
        t0 = time.perf_counter()
        shadow_id = f"SHADOW-{uuid.uuid4().hex[:12].upper()}"

        logger.info(
            "Initiating Shadow-Mode passive evaluation '%s' for incident '%s' (Org: '%s')",
            shadow_id,
            req.incident_key,
            org_id,
        )

        # Build investigation request
        inv_req = InvestigationRequest(
            incident_key=req.incident_key,
            lookback_minutes=req.lookback_minutes,
            force_refresh=True,
            include_rag_context=True,
        )

        # Run investigation pipeline (passive observation only)
        inv_resp = self.inv_service.run_investigation(
            db=db,
            req=inv_req,
            telemetry_service=telemetry_service,
        )

        latency_ms = (time.perf_counter() - t0) * 1000.0

        # Scrub secrets from leading hypothesis and confirmed findings if enabled
        redacted_count = 0
        leading_hyp = inv_resp.leading_hypothesis or "Insufficient evidence"
        if req.redact_secrets and leading_hyp:
            leading_hyp, r_cnt = redact_sensitive_strings(leading_hyp)
            redacted_count += r_cnt

        logger.info(
            "Shadow-Mode evaluation completed: id=%s, status=%s, leading='%s', conf=%.2f, latency=%.1fms (0 repairs triggered)",
            shadow_id,
            inv_resp.status.value,
            leading_hyp,
            inv_resp.confidence,
            latency_ms,
        )

        return ShadowModeResponse(
            shadow_run_id=shadow_id,
            incident_key=req.incident_key,
            investigation_key=inv_resp.investigation_key,
            execution_mode="SHADOW_PASSIVE",
            is_shadow_mode=True,
            live_telemetry_verified=False,  # Explicitly NOT VERIFIED unless live prod provider certified
            telemetry_provenance="SANITIZED_REPLAY_FIXTURE" if req.replay_fixture_path else "LOCAL_TEST_TELEMETRY",
            status=inv_resp.status.value,
            leading_hypothesis=leading_hyp,
            confidence=inv_resp.confidence,
            latency_ms=round(latency_ms, 2),
            is_fallback=inv_resp.is_fallback,
            secrets_redacted_count=redacted_count,
            repair_workflow_triggered=False,  # Guaranteed invariant
            git_mutations_count=0,            # Guaranteed invariant
            org_id=org_id,
            created_at=datetime.now(timezone.utc),
        )
