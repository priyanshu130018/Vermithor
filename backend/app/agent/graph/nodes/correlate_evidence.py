from datetime import datetime, timezone
import logging
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agent.graph.state import InvestigationState
from backend.app.correlation.db.models import CorrelationGroup
from backend.app.correlation.schemas.correlation import SignalInput, SignalType
from backend.app.correlation.services.correlation_service import CorrelationService

logger = logging.getLogger(__name__)


def correlate_evidence_node(
    state: InvestigationState,
    db: Optional[Session] = None,
    correlation_service: Optional[CorrelationService] = None,
) -> Dict[str, Any]:
    """
    Step 4: Correlate evidence signals by reusing Vermithor's existing CorrelationService
    and multi-factor CorrelationScorer.
    """
    service_name = state.get("target_service", "unknown")
    environment = state.get("environment", "production")
    incident_key = state.get("incident_key", "UNKNOWN")
    collected_evidence: List[Dict[str, Any]] = list(state.get("collected_evidence", []))

    corr_svc = correlation_service or CorrelationService()
    now = datetime.now(timezone.utc)

    # 1. Check if correlation group is already associated with this incident
    group_key = None
    group_score = 0.0
    group_reasons: List[str] = []

    if db is not None:
        try:
            existing_grp = db.execute(
                select(CorrelationGroup)
                .where(
                    (CorrelationGroup.incident_key == incident_key)
                    | ((CorrelationGroup.incident_key.is_(None)) & (CorrelationGroup.primary_service == service_name))
                )
                .order_by(CorrelationGroup.group_key.asc())
            ).scalars().first()
            if existing_grp:
                group_key = existing_grp.group_key
                group_score = existing_grp.correlation_score
                group_reasons = existing_grp.reasons or []
        except Exception as exc:
            logger.debug("Could not query existing correlation group: %s", exc)

    # 2. Convert collected evidence items to SignalInput for scoring
    signals: List[SignalInput] = []
    for ev in collected_evidence:
        stype_str = ev.get("source_type", "EVENT")
        sig_type = SignalType.METRIC if "METRIC" in stype_str or "PROM" in stype_str else (
            SignalType.TRACE if "TRACE" in stype_str else (
                SignalType.DEPLOYMENT if "DEPLOY" in stype_str else SignalType.EVENT
            )
        )
        ts_str = ev.get("timestamp")
        ts = datetime.fromisoformat(ts_str) if ts_str else now
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        signals.append(
            SignalInput(
                signal_id=ev.get("source_id", ev.get("evidence_id")),
                signal_type=sig_type,
                timestamp=ts,
                service=ev.get("service") or service_name,
                environment=environment,
                severity="ERROR" if "anom" in ev.get("evidence_id", "").lower() or "error" in ev.get("claim", "").lower() else "INFO",
                source_reference=ev.get("source_id"),
                metadata=ev.get("data", {}),
            )
        )

    # 3. Evaluate correlation score if not already known
    if signals and (group_score == 0.0 or not group_reasons):
        try:
            score, is_correlated, reasons = corr_svc.evaluate_signals(signals)
            group_score = score
            group_reasons = reasons
            if not group_key:
                group_key = f"GRP-{incident_key}"
        except Exception as exc:
            logger.warning("Error evaluating correlation signals: %s", exc)
            group_reasons = [f"Signal count: {len(signals)}"]
            group_score = 0.75 if len(signals) > 1 else 0.40

    # Add correlation evidence item only if we have correlated signals
    if signals:
        seen_ids = {e.get("source_id") for e in collected_evidence}
        corr_src_id = f"corr-{group_key or incident_key}"
        if corr_src_id not in seen_ids:
            collected_evidence.append({
                "evidence_id": f"EV-CORR-{len(collected_evidence) + 1}",
                "source_type": "CORRELATION",
                "source_id": corr_src_id,
                "service": service_name,
                "timestamp": now.isoformat(),
                "claim": f"Correlation group {group_key or 'N/A'}: score={group_score:.2f}. Reasons: {'; '.join(group_reasons[:3])}",
                "data": {
                    "group_key": group_key,
                    "correlation_score": group_score,
                    "reasons": group_reasons,
                    "signal_count": len(signals),
                },
            })

    logger.info(
        "Evidence correlation completed for %s: group=%s, score=%.2f, reasons=%d",
        incident_key,
        group_key,
        group_score,
        len(group_reasons),
    )

    return {
        "correlation_group_key": group_key,
        "correlation_score": group_score,
        "correlation_reasons": group_reasons,
        "collected_evidence": collected_evidence,
    }
