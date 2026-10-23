"""
Track B: Held-Out DNS & Kafka Generalization Evaluation Harness.

Evaluates 4 unseen held-out scenarios (2 positive cases + 2 negative controls)
using the LangGraph investigation agent under supervised, read-only replay mode.
Verifies candidate coverage, ranking, Top-1 accuracy, Top-3 recall, MRR, citation validity,
and negative control discrimination without data leakage.
"""

from datetime import datetime, timezone
import json
from math import ceil
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Tuple
import yaml

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import backend.app.ingestion.db.models
import backend.app.incidents.db.models
import backend.app.anomaly.db.models
import backend.app.correlation.db.models
import backend.app.rca.db.models
import backend.app.log_intelligence.db.models
import backend.app.retrieval.db.models
import backend.app.summary.db.models
import backend.app.agent.db.models

from backend.app.common.database import Base
from backend.app.incidents.db.models import Incident
from backend.app.incidents.schemas.incident import IncidentCreate, IncidentSeverity
from backend.app.incidents.services.incident_service import IncidentService
from backend.app.ingestion.db.models import Event
from backend.app.observability.services.telemetry_service import TelemetryEvidenceService
from backend.app.agent.schemas.investigation import InvestigationRequest, InvestigationStatus
from backend.app.agent.services.investigation_service import InvestigationService
from backend.app.agent.services.pilot_service import PilotService
from backend.app.agent.services.citation_validator import EvidenceCitationValidator


class ScenarioReplayTelemetryService(TelemetryEvidenceService):
    """Telemetry service that serves signals strictly from the scenario fixture."""

    def __init__(self, agent_input: Dict[str, Any]):
        self.agent_input = agent_input
        self.metrics_list = agent_input.get("metrics", [])
        self.logs_list = agent_input.get("logs", [])
        self.service_name = agent_input.get("service", "unknown")

    def get_telemetry_snapshot(self, service: str, lookback_minutes: int = 15) -> Dict[str, Any]:
        now = datetime.now(timezone.utc)
        prom_metrics = {}
        for m in self.metrics_list:
            m_svc = m.get("service") or self.service_name
            if m_svc == service or m_svc == self.service_name:
                prom_metrics[m["metric_name"]] = {
                    "value": float(m["value"]),
                    "query": m["metric_name"],
                    "timestamp": m.get("timestamp") or now.isoformat(),
                }

        trace_summaries = []
        for i, l in enumerate(self.logs_list):
            if l.get("level") in ("ERROR", "CRITICAL", "WARN"):
                trace_summaries.append({
                    "trace_id": f"trace-{service[:8]}-{i:04d}",
                    "root_service": service,
                    "root_operation": f"HANDLE /{service}",
                    "start_time": l.get("timestamp") or now.isoformat(),
                    "duration_ms": 1500.0 if l.get("level") == "WARN" else 4500.0,
                    "span_count": 8,
                    "services_involved": [service],
                    "has_error": l.get("level") in ("ERROR", "CRITICAL"),
                    "error_spans": [{"span_id": f"sp-{i}", "error_message": l.get("message")}],
                    "bottleneck_spans": [],
                })

        return {
            "service": service,
            "lookback_minutes": lookback_minutes,
            "collected_at": now.isoformat(),
            "sources": {
                "prometheus": {
                    "base_url": "http://sanitized-replay-fixture:9090",
                    "metrics": prom_metrics,
                },
                "jaeger": {
                    "base_url": "http://sanitized-replay-fixture:16686",
                    "total_traces": len(trace_summaries),
                    "summaries": trace_summaries,
                },
            },
        }


def seed_held_out_incident(db, scenario_data: Dict[str, Any], tenant_id: str) -> Incident:
    agent_input = scenario_data["agent_input"]
    inc_key = agent_input["incident_key"]
    now = datetime.now(timezone.utc)

    inc_in = IncidentCreate(
        incident_key=inc_key,
        title=f"Held-out Incident: {scenario_data['scenario_name']}",
        description=f"Automated evaluation incident for scenario {scenario_data['id']}",
        severity=IncidentSeverity.SEV1 if scenario_data.get("severity") == "CRITICAL" else IncidentSeverity.SEV2,
        environment=scenario_data.get("environment", "production"),
        started_at=now,
        confidence=0.90,
    )
    inc = IncidentService.create_incident(db, inc_in)

    # Ingest logs
    for i, log_item in enumerate(agent_input.get("logs", [])):
        log_ts_str = log_item.get("timestamp")
        log_ts = datetime.fromisoformat(log_ts_str.replace("Z", "+00:00")) if log_ts_str else now
        evt = Event(
            event_id=f"evt-{inc_key}-{i:04d}",
            timestamp=log_ts,
            service=log_item.get("service") or agent_input["service"],
            environment=scenario_data.get("environment", "production"),
            event_type="LOG",
            severity=log_item.get("level", "INFO"),
            message=log_item.get("message", ""),
            metadata_json={"source": "held_out_logs", "raw": log_item, "org_id": tenant_id},
        )
        db.add(evt)

    # Ingest deployments
    for i, dep in enumerate(agent_input.get("deployments", [])):
        dep_ts_str = dep.get("timestamp")
        dep_ts = datetime.fromisoformat(dep_ts_str.replace("Z", "+00:00")) if dep_ts_str else now
        dep_evt = Event(
            event_id=f"dep-{inc_key}-{i:04d}",
            timestamp=dep_ts,
            service=dep.get("service") or agent_input["service"],
            environment=scenario_data.get("environment", "production"),
            event_type="DEPLOYMENT",
            severity="INFO",
            message=f"Deployment {dep.get('version')}: {dep.get('change_summary')}",
            metadata_json={"version": dep.get("version"), "summary": dep.get("change_summary"), "org_id": tenant_id},
        )
        db.add(dep_evt)

    db.commit()
    return inc


def run_held_out_evaluation() -> Dict[str, Any]:
    print("=" * 80)
    print("TRACK B: HELD-OUT DNS & KAFKA GENERALIZATION EVALUATION")
    print("=" * 80)

    # 1. Establish isolated database
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()

    tenant_id = "held_out_eval_tenant"
    operator_id = "ml_eval_lead"

    # Governance Policy
    pilot_service = PilotService()
    policy = pilot_service.get_or_create_policy(db, tenant_id)
    policy.acknowledged_read_only = True
    policy.acknowledged_by = operator_id
    policy.acknowledged_at = datetime.now(timezone.utc)
    policy.collection_enabled = False
    policy.allow_external_llm = False
    policy.redact_sensitive_fields = True
    policy.retention_days = 30
    db.commit()

    # Load Ground Truth answer keys
    gt_path = REPO_ROOT / "evaluation" / "benchmarks" / "held_out_fixtures" / "ground_truth" / "answer_keys.json"
    with open(gt_path, "r", encoding="utf-8") as f:
        answer_keys = json.load(f)

    # Load Scenarios
    scenarios_dir = REPO_ROOT / "evaluation" / "benchmarks" / "held_out_fixtures" / "scenarios"
    scenario_files = sorted(list(scenarios_dir.glob("held_out_case_*.yaml")))

    print(f"Loaded {len(scenario_files)} held-out scenario fixtures.")
    print(f"Loaded {len(answer_keys)} held-out ground-truth answer keys.")

    inv_service = InvestigationService()

    case_results = []
    latencies = []
    candidate_generation_hits = 0
    top_1_hits = 0
    top_3_hits = 0
    mrr_sum = 0.0
    total_citations = 0
    valid_citations = 0
    unsupported_claims_count = 0
    negative_control_passed_count = 0
    negative_control_total = 0

    for idx, scn_file in enumerate(scenario_files):
        with open(scn_file, "r", encoding="utf-8") as f:
            scn = yaml.safe_load(f)

        inc_key = scn["agent_input"]["incident_key"]
        case_id = scn["id"]
        target_service = scn["target_service"]
        gt = answer_keys[inc_key]
        is_neg_ctrl = gt.get("is_negative_control", False)

        if is_neg_ctrl:
            negative_control_total += 1

        print(f"\n--- [{idx+1}/{len(scenario_files)}] Running {case_id} ({inc_key}: {target_service}) ---")
        if is_neg_ctrl:
            print(f"  [NEGATIVE CONTROL]: Prohibited keywords: {gt.get('prohibited_root_cause_keywords')}")

        # Seed Database
        seed_held_out_incident(db, scn, tenant_id)

        # Build Replay Telemetry Service
        telemetry_svc = ScenarioReplayTelemetryService(scn["agent_input"])

        # Execute Pipeline with timing
        t0 = time.perf_counter()
        req = InvestigationRequest(
            incident_key=inc_key,
            lookback_minutes=scn["agent_input"]["lookback_minutes"],
            force_refresh=True,
            include_rag_context=True,
        )
        inv_resp = inv_service.run_investigation(
            db=db,
            req=req,
            telemetry_service=telemetry_svc,
            org_id=tenant_id,
        )
        t1 = time.perf_counter()
        latency_ms = (t1 - t0) * 1000.0
        latencies.append(latency_ms)

        leading_hyp = inv_resp.leading_hypothesis or "Insufficient evidence"
        leading_hyp_lower = leading_hyp.lower()
        conf = inv_resp.confidence

        expected_kws = [k.lower() for k in gt.get("expected_root_cause_keywords", [])]
        prohibited_kws = [k.lower() for k in gt.get("prohibited_root_cause_keywords", [])]

        # 1. Candidate Generation Coverage Check
        # Did the RCA candidate generator produce a candidate matching expected root cause keywords?
        rep = inv_resp.report
        eval_hyps = rep.hypotheses_evaluated if rep else []
        candidate_names = [(h.hypothesis or "").lower() for h in eval_hyps]
        candidate_count = len(eval_hyps)

        cause_in_candidates = any(any(kw in c for kw in expected_kws) for c in candidate_names)
        if cause_in_candidates:
            candidate_generation_hits += 1

        # 2. Top-1 and Negative Control Discrimination Check
        matched_expected = any(kw in leading_hyp_lower for kw in expected_kws)
        triggered_prohibited = any(pkw in leading_hyp_lower for pkw in prohibited_kws)

        if is_neg_ctrl:
            neg_passed = (matched_expected and not triggered_prohibited)
            if neg_passed:
                negative_control_passed_count += 1
            top_1_hit = neg_passed
        else:
            top_1_hit = matched_expected

        # 3. Top-3 and MRR Check
        top_3_hit = False
        mrr = 0.0
        if top_1_hit:
            top_3_hit = True
            mrr = 1.0
        else:
            for rank_idx, c_name in enumerate(candidate_names[:3]):
                if any(kw in c_name for kw in expected_kws) and not any(pkw in c_name for pkw in prohibited_kws):
                    top_3_hit = True
                    mrr = 1.0 / (rank_idx + 1)
                    break

        if top_1_hit:
            top_1_hits += 1
        if top_3_hit:
            top_3_hits += 1
        mrr_sum += mrr

        # 4. Strict Citation Audit using EvidenceCitationValidator
        ev_items_dict = [e.model_dump() for e in (rep.evidence_items if rep else [])]
        hyps_dict = [h.model_dump() for h in eval_hyps]

        citation_audit = EvidenceCitationValidator.audit_investigation(
            evidence_items=ev_items_dict,
            hypotheses=hyps_dict,
            tenant_id=tenant_id,
            incident_key=inc_key,
            raw_telemetry=scn["agent_input"],
            db=db,
        )

        total_citations += citation_audit["total_citations_evaluated"]
        valid_citations += citation_audit["valid_citations_count"]

        # Unsupported claims check
        findings = rep.confirmed_findings if rep else []
        for finding in findings:
            f_lower = finding.lower()
            if not any(token in f_lower for token in ["evidence", "metric", "telemetry", "confirmed", "observed", "trace", "log"]):
                unsupported_claims_count += 1

        print(f"  Leading Hypothesis: {leading_hyp}")
        print(f"  Confidence: {conf:.2f} | Latency: {latency_ms:.1f}ms")
        print(f"  Candidate Coverage: {cause_in_candidates} (Candidates: {candidate_count})")
        print(f"  Top-1 Hit: {top_1_hit} | Top-3 Hit: {top_3_hit} | MRR: {mrr:.2f}")
        print(f"  Citation Validity: {citation_audit['valid_citations_count']}/{citation_audit['total_citations_evaluated']} ({citation_audit['citation_validity_rate']:.1%})")

        case_results.append({
            "case_id": case_id,
            "incident_key": inc_key,
            "service": target_service,
            "is_negative_control": is_neg_ctrl,
            "injected_cause": gt["injected_cause"],
            "leading_hypothesis": leading_hyp,
            "confidence": round(conf, 4),
            "candidate_coverage": cause_in_candidates,
            "candidate_count": candidate_count,
            "ranked_candidates": [h.hypothesis for h in eval_hyps],
            "top_1_hit": top_1_hit,
            "top_3_hit": top_3_hit,
            "mrr": round(mrr, 4),
            "latency_ms": round(latency_ms, 2),
            "citation_audit": {
                "total_citations": citation_audit["total_citations_evaluated"],
                "valid_citations": citation_audit["valid_citations_count"],
                "invalid_citations": citation_audit["invalid_citations_count"],
                "validity_rate": citation_audit["citation_validity_rate"],
                "breakdown": citation_audit["breakdown"],
                "uncited_material_count": citation_audit["uncited_material_count"],
            },
        })

    n_cases = len(case_results)
    sorted_lat = sorted(latencies)
    p50_lat = sorted_lat[len(sorted_lat) // 2]
    p90_lat = sorted_lat[min(len(sorted_lat) - 1, int(ceil(0.90 * len(sorted_lat))) - 1)]

    summary = {
        "metadata": {
            "evaluation_title": "Track B: Held-Out DNS & Kafka Generalization Benchmark",
            "evaluation_date": datetime.now(timezone.utc).isoformat(),
            "sample_size": n_cases,
            "dataset_version": "1.0.0",
            "pilot_mode": "SUPERVISED_READ_ONLY_REPLAY",
            "tenant_id": tenant_id,
        },
        "metrics": {
            "cases_evaluated_total": n_cases,
            "candidate_generation_coverage": {
                "numerator": candidate_generation_hits,
                "denominator": n_cases,
                "rate": round(candidate_generation_hits / n_cases, 4),
            },
            "top_1_diagnosis_accuracy": {
                "numerator": top_1_hits,
                "denominator": n_cases,
                "rate": round(top_1_hits / n_cases, 4),
            },
            "top_3_diagnosis_recall": {
                "numerator": top_3_hits,
                "denominator": n_cases,
                "rate": round(top_3_hits / n_cases, 4),
            },
            "mean_reciprocal_rank": round(mrr_sum / n_cases, 4),
            "negative_control_discrimination": {
                "numerator": negative_control_passed_count,
                "denominator": negative_control_total,
                "rate": round(negative_control_passed_count / negative_control_total, 4) if negative_control_total else 1.0,
            },
            "evidence_citation_validity": {
                "numerator": valid_citations,
                "denominator": total_citations,
                "rate": round(valid_citations / total_citations, 4) if total_citations else 1.0,
            },
            "unsupported_claims_count": unsupported_claims_count,
            "latency_ms": {
                "min": round(min(latencies), 2),
                "median_p50": round(p50_lat, 2),
                "p90": round(p90_lat, 2),
                "max": round(max(latencies), 2),
                "average": round(sum(latencies) / n_cases, 2),
            },
        },
        "cases": case_results,
    }

    out_file = REPO_ROOT / "evaluation" / "results" / "held_out_dns_kafka_evaluation.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nWrote held-out evaluation results to {out_file}")

    return summary


if __name__ == "__main__":
    run_held_out_evaluation()
