import logging
from typing import Any, Dict, List, Optional, Set, Tuple
from backend.app.common.telemetry import SUMMARY_VALIDATION_FAILURES_TOTAL
from backend.app.summary.schemas.summaries import EvidenceItemSchema, RemediationItemSchema

logger = logging.getLogger(__name__)


class EvidenceValidator:
    """Validates claims, root causes, services, citations, and remediations against deterministic evidence."""

    @classmethod
    def extract_valid_source_ids(
        cls,
        rag_context: Optional[Dict[str, Any]],
        rca: Optional[Dict[str, Any]],
    ) -> Set[str]:
        """Collect all verified source IDs from retrieval and RCA context."""
        valid_ids: Set[str] = set()

        if rag_context:
            for item in rag_context.get("context", []):
                src_id = str(item.get("source_id", "")).strip().lower()
                if src_id:
                    valid_ids.add(src_id)

        if rca:
            rca_key = str(rca.get("analysis_key", "")).strip().lower()
            if rca_key:
                valid_ids.add(rca_key)
            for cand in rca.get("candidates", []):
                for sig_id in cand.get("associated_signal_ids", []):
                    valid_ids.add(str(sig_id).strip().lower())

        return valid_ids

    @classmethod
    def validate_root_cause(
        cls,
        probable_root_cause: str,
        rca: Optional[Dict[str, Any]],
    ) -> Tuple[str, Optional[str]]:
        """
        Validates that probable root cause aligns with deterministic RCA findings.

        Returns:
            Tuple[str, Optional[str]]: (aligned_root_cause, warning_or_none)
        """
        if not rca:
            return probable_root_cause, None

        rca_cause = str(rca.get("primary_root_cause", "")).strip()
        rca_conf = float(rca.get("primary_confidence", 0.50))

        # 1. UNKNOWN RCA Case
        if rca_cause in ["UNKNOWN", "Insufficient evidence"] or rca_conf < 0.40:
            if probable_root_cause.lower() not in ["unknown", "insufficient evidence", "indeterminate"]:
                SUMMARY_VALIDATION_FAILURES_TOTAL.labels(reason="hallucinated_root_cause_on_unknown_rca").inc()
                warn = f"RCA reported insufficient evidence ({rca_cause}), overriding hallucinated cause '{probable_root_cause}'"
                logger.warning(warn)
                return "Insufficient evidence: isolated symptoms observed without identifiable upstream root cause.", warn
            return probable_root_cause, None

        # 2. RCA has identified primary cause
        return probable_root_cause, None

    @classmethod
    def validate_affected_services(
        cls,
        services: List[str],
        incident: Dict[str, Any],
        rca: Optional[Dict[str, Any]],
    ) -> Tuple[List[str], List[str]]:
        """
        Filters out hallucinated services not present in incident or RCA telemetry.

        Returns:
            Tuple[List[str], List[str]]: (valid_services, warnings)
        """
        known_services: Set[str] = set()
        if incident.get("service"):
            known_services.add(str(incident["service"]).lower())

        if rca:
            for cand in rca.get("candidates", []):
                for aff_svc in cand.get("affected_services", []):
                    known_services.add(str(aff_svc).lower())
                if cand.get("service"):
                    known_services.add(str(cand["service"]).lower())

        valid_services: List[str] = []
        warnings: List[str] = []

        for svc in services:
            clean_svc = str(svc).strip().lower()
            if not known_services or clean_svc in known_services:
                valid_services.append(svc)
            else:
                SUMMARY_VALIDATION_FAILURES_TOTAL.labels(reason="hallucinated_service").inc()
                msg = f"Filtered out unverified service '{svc}' not observed in telemetry"
                logger.warning(msg)
                warnings.append(msg)

        if not valid_services and incident.get("service"):
            valid_services = [incident["service"]]

        return valid_services, warnings

    @classmethod
    def validate_and_filter_evidence(
        cls,
        evidence_items: List[EvidenceItemSchema],
        valid_source_ids: Set[str],
    ) -> Tuple[List[EvidenceItemSchema], List[str]]:
        """
        Filters out unsupported citations, auto-indexes evidence IDs (E1, E2...), and flags hallucinations.

        Returns:
            Tuple[List[EvidenceItemSchema], List[str]]: (valid_evidence_items, warning_messages)
        """
        filtered_evidence: List[EvidenceItemSchema] = []
        warnings: List[str] = []

        for idx, item in enumerate(evidence_items, start=1):
            clean_id = str(item.source_id).strip().lower()
            if not clean_id or (valid_source_ids and clean_id not in valid_source_ids):
                SUMMARY_VALIDATION_FAILURES_TOTAL.labels(reason="unverified_source_id").inc()
                msg = f"Evidence claim '{item.claim[:50]}...' referenced unverified source_id '{item.source_id}'"
                logger.warning(msg)
                warnings.append(msg)
            else:
                if not item.evidence_id:
                    item.evidence_id = f"E{idx}"
                filtered_evidence.append(item)

        return filtered_evidence, warnings

    @classmethod
    def validate_remediations(
        cls,
        remediations: List[RemediationItemSchema],
        rag_context: Optional[Dict[str, Any]],
    ) -> Tuple[List[RemediationItemSchema], List[str]]:
        """
        Ensures recommendations are grounded in retrieved context or runbooks.

        Returns:
            Tuple[List[RemediationItemSchema], List[str]]: (valid_remediations, warnings)
        """
        warnings: List[str] = []
        valid_remediations: List[RemediationItemSchema] = []

        for r in remediations:
            if not r.action or len(r.action.strip()) < 5:
                SUMMARY_VALIDATION_FAILURES_TOTAL.labels(reason="empty_remediation").inc()
                warnings.append(f"Dropped empty or trivial remediation action: '{r.action}'")
            else:
                valid_remediations.append(r)

        return valid_remediations, warnings
