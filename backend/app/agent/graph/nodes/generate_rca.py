import logging
from typing import Any, Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.app.agent.graph.state import InvestigationState
from backend.app.rca.analysis.analyzer import RCAAnalyzer
from backend.app.rca.db.models import RCAAnalysis

logger = logging.getLogger(__name__)


def generate_rca_node(
    state: InvestigationState,
    db: Optional[Session] = None,
    rca_analyzer: Optional[RCAAnalyzer] = None,
) -> Dict[str, Any]:
    """
    Step 5: Invoke Vermithor's existing RCA engine to construct the causal DAG
    and retrieve its ranked root-cause candidates and original confidence scores.
    """
    group_key = state.get("correlation_group_key") or f"GRP-{state.get('incident_key', 'UNKNOWN')}"
    target_svc = state.get("target_service", "unknown")
    collected_evidence: List[Dict[str, Any]] = list(state.get("collected_evidence", []))
    raw_traces: List[Dict[str, Any]] = list(state.get("raw_traces", []))

    analyzer = rca_analyzer or RCAAnalyzer()

    # 1. Check if RCA analysis already exists in database for this correlation group
    db_candidates: List[Dict[str, Any]] = []
    db_edges: List[Dict[str, Any]] = []
    db_chain: List[Dict[str, Any]] = []
    primary_cause = None
    primary_conf = 0.0

    if db is not None and not state.get("force_refresh", False):
        try:
            existing_rca = db.execute(
                select(RCAAnalysis)
                .options(selectinload(RCAAnalysis.candidates), selectinload(RCAAnalysis.edges))
                .where(RCAAnalysis.group_key == group_key)
            ).scalar_one_or_none()

            if existing_rca and existing_rca.candidates:
                primary_cause = existing_rca.primary_root_cause
                primary_conf = existing_rca.primary_confidence
                db_chain = existing_rca.causal_chain or []
                for cand in existing_rca.candidates:
                    db_candidates.append({
                        "candidate_name": cand.candidate_name,
                        "candidate_type": cand.candidate_type,
                        "confidence": cand.confidence,
                        "evidence_signal_ids": cand.evidence_signal_ids or [],
                        "reasoning": cand.reasoning,
                    })
                for edge in existing_rca.edges:
                    db_edges.append({
                        "source": edge.source_node,
                        "target": edge.target_node,
                        "weight": edge.weight,
                        "relationship": edge.relationship_type,
                    })
        except Exception as exc:
            logger.debug("Could not read existing RCA from DB: %s", exc)

    # 2. If no persisted RCA, execute analyzer dynamically
    if not db_candidates:
        # Build signals structure from collected evidence
        # Filter for actual signals (exclude CORRELATION, RCA, etc.)
        valid_signal_types = {
            "METRIC_OBSERVATION", "PROMETHEUS", "EVENT", "DEPLOYMENT",
            "TRACE", "JAEGER", "ANOMALY", "INCIDENT_EVENT",
        }
        signals: List[Dict[str, Any]] = []
        for ev in collected_evidence:
            stype = ev.get("source_type", "EVENT")
            if stype in valid_signal_types:
                ts = ev.get("timestamp")
                if not ts or str(ts) == "None":
                    from datetime import datetime, timezone
                    ts = datetime.now(timezone.utc).isoformat()
                elif hasattr(ts, "isoformat"):
                    ts = ts.isoformat()
                data = ev.get("data", {})
                raw_sev = str(data.get("severity") or ev.get("severity") or "").upper()
                if raw_sev in ("CRITICAL", "ERROR", "FATAL"):
                    sev = "ERROR"
                elif raw_sev in ("WARN", "WARNING"):
                    sev = "WARN"
                elif stype == "ANOMALY":
                    sev = "ERROR"
                elif stype in ("PROMETHEUS", "METRIC_OBSERVATION"):
                    m_val = data.get("value")
                    m_name = str(data.get("metric_name", "")).lower()
                    try:
                        fval = float(m_val) if m_val is not None else 0.0
                    except (ValueError, TypeError):
                        fval = 0.0
                    if ("error" in m_name or "5xx" in m_name or "401" in m_name or "loss" in m_name) and fval >= 0.05:
                        sev = "ERROR"
                    elif ("utilization" in m_name or "ratio" in m_name) and fval >= 0.85:
                        sev = "ERROR"
                    elif ("latency" in m_name or "duration" in m_name) and fval >= 1000.0:
                        sev = "ERROR"
                    elif ("rate" in m_name or "retrans" in m_name) and fval >= 1000.0:
                        sev = "ERROR"
                    else:
                        sev = "INFO"
                elif "error" in ev.get("claim", "").lower() and stype not in ("PROMETHEUS", "METRIC_OBSERVATION"):
                    sev = "ERROR"
                else:
                    sev = "INFO"

                signals.append({
                    "signal_id": ev.get("source_id", ev.get("evidence_id")),
                    "signal_type": stype,
                    "timestamp": str(ts),
                    "service": ev.get("service") or target_svc,
                    "severity": sev,
                    "source_reference": ev.get("source_id"),
                    "message": data.get("message") or ev.get("claim", ""),
                    "metadata": data,
                })

        if not signals:
            primary_cause = "Insufficient evidence"
            primary_conf = 0.10
            db_candidates = [{
                "candidate_name": "Insufficient evidence",
                "candidate_type": "UNKNOWN",
                "confidence": 0.10,
                "evidence_signal_ids": [],
                "reasoning": "No telemetry signals or anomaly observations were available for root cause analysis.",
            }]
        else:
            group_data = {
                "group_key": group_key,
                "primary_service": target_svc,
                "signals": signals,
                "traces": raw_traces,
            }

            try:
                analysis_output = analyzer.analyze(group_data)
                primary_cause = analysis_output.get("primary_root_cause")
                primary_conf = analysis_output.get("primary_confidence", 0.0)
                db_candidates = analysis_output.get("candidates", [])
                db_edges = analysis_output.get("edges", [])
                db_chain = analysis_output.get("causal_chain", [])
            except Exception as exc:
                logger.error("RCA analysis invocation failed: %s", exc)
                primary_cause = "Insufficient evidence"
                primary_conf = 0.10
                db_candidates = [{
                    "candidate_name": "Insufficient evidence",
                    "candidate_type": "UNKNOWN",
                    "confidence": 0.10,
                    "evidence_signal_ids": [],
                    "reasoning": f"RCA evaluation exception: {exc}",
                }]

    # 3. Add RCA candidates as evidence items
    seen_ids = {e.get("source_id") for e in collected_evidence}
    for idx, cand in enumerate(db_candidates[:3], start=1):
        cand_name = cand.get("candidate_name", "Unknown")
        cand_type = cand.get("candidate_type", "UNKNOWN")
        cand_score = cand.get("confidence", 0.0)
        src_id = f"rca-cand-{idx}-{cand_type}"
        if src_id not in seen_ids:
            seen_ids.add(src_id)
            collected_evidence.append({
                "evidence_id": f"EV-RCA-{idx}",
                "source_type": "RCA",
                "source_id": src_id,
                "service": target_svc,
                "timestamp": None,
                "claim": f"RCA Candidate #{idx}: '{cand_name}' (Type: {cand_type}, Original Score: {cand_score:.4f})",
                "data": cand,
            })

    logger.info(
        "RCA candidate generation completed: primary='%s', confidence=%.2f, candidates=%d",
        primary_cause,
        primary_conf,
        len(db_candidates),
    )

    return {
        "primary_root_cause": primary_cause,
        "primary_confidence": primary_conf,
        "rca_candidates": db_candidates,
        "causal_chain": db_chain,
        "causal_edges": db_edges,
        "collected_evidence": collected_evidence,
    }
