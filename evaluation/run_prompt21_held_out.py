"""
Evaluation runner for Prompt 21 Frozen Held-Out Generalization Benchmark.
Evaluates 8 unseen held-out cases across memory, deployment, storage, kafka, dns, and negative controls.
"""

from datetime import datetime, timezone
import hashlib
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any, Dict, List
import yaml

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.WARNING, format="%(asctime)s [%(levelname)s] %(message)s")

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
from backend.app.agent.schemas.investigation import InvestigationRequest
from backend.app.agent.services.investigation_service import InvestigationService
from backend.app.agent.services.pilot_service import PilotService
from backend.app.agent.services.citation_validator import EvidenceCitationValidator
from evaluation.run_blind_evaluation import BlindReplayTelemetryService, seed_blind_incident


def run_held_out_evaluation():
    print("=" * 80)
    print("PROMPT 21 FROZEN HELD-OUT GENERALIZATION BENCHMARK (N=8 CASES)")
    print("=" * 80)

    benchmark_dir = REPO_ROOT / "evaluation" / "benchmarks" / "prompt21_held_out_fixtures"
    manifest_file = benchmark_dir / "manifest.json"
    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest_data = json.load(f)

    # Cryptographic integrity check
    gt_file = benchmark_dir / manifest_data["answer_keys_file"]
    with open(gt_file, "rb") as f:
        computed_hash = hashlib.sha256(f.read()).hexdigest()
    assert computed_hash == manifest_data["answer_keys_sha256"], "Held-out ground truth checksum mismatch!"

    with open(gt_file, "r", encoding="utf-8") as f:
        ground_truth = json.load(f)

    scenarios_dir = benchmark_dir / "scenarios"
    scenario_files = sorted(list(scenarios_dir.glob("held_p21_*.yaml")))
    print(f"Verified manifest SHA-256: {computed_hash[:16]}... ({len(scenario_files)} scenarios loaded)\n")

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()

    tenant_id = "prompt21_held_out_tenant"
    operator_id = "independent_evaluator"

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

    inv_service = InvestigationService()

    case_results = []
    latencies = []
    total_candidate_hits = 0
    total_top1_hits = 0
    total_top3_hits = 0
    total_mrr = 0.0

    neg_controls_total = 0
    neg_controls_safety_passed = 0
    neg_controls_diagnostic_passed = 0

    total_citations = 0
    total_valid_telemetry = 0
    total_historical_analogies = 0
    total_missing_unresolved = 0

    for idx, scn_path in enumerate(scenario_files):
        with open(scn_path, "r", encoding="utf-8") as f:
            scn = yaml.safe_load(f)

        case_id = scn["id"]
        inc_key = scn["agent_input"]["incident_key"]
        svc = scn["target_service"]
        fam = scn["root_cause_family"]
        is_neg = scn.get("is_negative_control", False)

        gt = ground_truth[inc_key]
        expected_kws = [k.lower() for k in gt["expected_root_cause_keywords"]]
        prohibited_kws = [k.lower() for k in gt["prohibited_root_cause_keywords"]]

        if is_neg:
            neg_controls_total += 1

        print(f"[{idx+1}/{len(scenario_files)}] {case_id} ({inc_key}: {svc}) [{fam}]")
        seed_blind_incident(db, scn, tenant_id)
        telemetry_svc = BlindReplayTelemetryService(scn["agent_input"])

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
        lat_ms = round((t1 - t0) * 1000.0, 2)
        latencies.append(lat_ms)

        leading_hyp = inv_resp.leading_hypothesis or "Insufficient evidence"
        leading_hyp_lower = leading_hyp.lower()
        conf = round(float(inv_resp.confidence), 4)

        rep = inv_resp.report
        eval_hyps = rep.hypotheses_evaluated if rep else []
        cand_names = [(h.hypothesis or "").lower() for h in eval_hyps]

        # 1. Candidate coverage
        cand_coverage_hit = any(any(kw in c for kw in expected_kws) for c in cand_names)
        if cand_coverage_hit:
            total_candidate_hits += 1

        # 2. Top-1 hit
        matched_expected = any(kw in leading_hyp_lower for kw in expected_kws)
        triggered_prohibited = any(pkw in leading_hyp_lower for pkw in prohibited_kws)

        safety_pass = not triggered_prohibited
        diagnostic_pass = (matched_expected and not triggered_prohibited)

        if is_neg:
            if safety_pass:
                neg_controls_safety_passed += 1
            if diagnostic_pass:
                neg_controls_diagnostic_passed += 1
            top_1_hit = diagnostic_pass
        else:
            top_1_hit = matched_expected

        if top_1_hit:
            total_top1_hits += 1

        # 3. Top-3 Hit & MRR
        top_3_hit = False
        mrr = 0.0
        correct_rank = None
        if top_1_hit:
            top_3_hit = True
            mrr = 1.0
            correct_rank = 1
        else:
            for rank_idx, c_name in enumerate(cand_names[:3]):
                if any(kw in c_name for kw in expected_kws) and not any(pkw in c_name for pkw in prohibited_kws):
                    top_3_hit = True
                    mrr = round(1.0 / (rank_idx + 1), 4)
                    correct_rank = rank_idx + 1
                    break

        if top_3_hit:
            total_top3_hits += 1
        total_mrr += mrr

        # 4. Strict Citation Audit
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
        total_valid_telemetry += citation_audit["valid_citations_count"]
        bk = citation_audit["breakdown"]
        total_historical_analogies += bk["cross_incident"]
        total_missing_unresolved += bk["missing_or_unresolved"]

        print(f"  Leading: {leading_hyp} (conf={conf})")
        print(f"  Top-1: {top_1_hit} | Top-3: {top_3_hit} | Coverage: {cand_coverage_hit}")
        print(f"  Citations: {citation_audit['valid_citations_count']}/{citation_audit['total_citations_evaluated']} valid, {bk['missing_or_unresolved']} missing\n")

        case_results.append({
            "case_id": case_id,
            "incident_key": inc_key,
            "root_cause_family": fam,
            "scenario_name": scn["scenario_name"],
            "target_service": svc,
            "is_negative_control": is_neg,
            "leading_hypothesis": leading_hyp,
            "confidence": conf,
            "candidate_coverage": cand_coverage_hit,
            "top_1_hit": top_1_hit,
            "top_3_hit": top_3_hit,
            "mrr": mrr,
            "correct_candidate_rank": correct_rank,
            "safety_discrimination_pass": safety_pass if is_neg else None,
            "diagnostic_discrimination_pass": diagnostic_pass if is_neg else None,
            "latency_ms": lat_ms,
            "citation_audit": {
                "total_citations": citation_audit["total_citations_evaluated"],
                "valid_direct_telemetry": citation_audit["valid_citations_count"],
                "historical_rag_references": bk["cross_incident"],
                "missing_or_unresolved": bk["missing_or_unresolved"],
                "malformed": bk["malformed"],
                "cross_tenant": bk["cross_tenant"],
            }
        })

    num_cases = len(scenario_files)
    cov_rate = round(total_candidate_hits / num_cases, 4)
    top1_rate = round(total_top1_hits / num_cases, 4)
    top3_rate = round(total_top3_hits / num_cases, 4)
    mean_mrr = round(total_mrr / num_cases, 4)
    safety_rate = round(neg_controls_safety_passed / neg_controls_total, 4) if neg_controls_total else 1.0
    diag_rate = round(neg_controls_diagnostic_passed / neg_controls_total, 4) if neg_controls_total else 1.0

    print("=" * 80)
    print("PROMPT 21 HELD-OUT EVALUATION SUMMARY")
    print(f"Total Cases: {num_cases}")
    print(f"Candidate Coverage: {total_candidate_hits}/{num_cases} ({cov_rate * 100:.1f}%)")
    print(f"Top-1 Accuracy: {total_top1_hits}/{num_cases} ({top1_rate * 100:.1f}%)")
    print(f"Top-3 Recall: {total_top3_hits}/{num_cases} ({top3_rate * 100:.1f}%)")
    print(f"MRR: {mean_mrr}")
    print(f"Negative Control Safety Discrimination: {neg_controls_safety_passed}/{neg_controls_total} ({safety_rate * 100:.1f}%)")
    print(f"Negative Control Diagnostic Discrimination: {neg_controls_diagnostic_passed}/{neg_controls_total} ({diag_rate * 100:.1f}%)")
    print(f"Citation Validity: {total_valid_telemetry}/{total_citations} direct telemetry, {total_historical_analogies} historical, {total_missing_unresolved} missing")
    print("=" * 80)

    out_file = REPO_ROOT / "evaluation" / "results" / "prompt21_held_out_results.json"
    results_payload = {
        "metadata": {
            "evaluation_title": "Prompt 21 Frozen Held-Out Generalization Evaluation",
            "evaluation_date": datetime.now(timezone.utc).isoformat(),
            "manifest_checksum_sha256": manifest_data["answer_keys_sha256"],
            "total_cases_evaluated": num_cases,
            "negative_controls_count": neg_controls_total,
            "positive_cases_count": num_cases - neg_controls_total,
        },
        "summary_metrics": {
            "candidate_coverage_rate": cov_rate,
            "top_1_accuracy": top1_rate,
            "top_3_recall": top3_rate,
            "mean_reciprocal_rank": mean_mrr,
            "negative_control_safety_discrimination": safety_rate,
            "negative_control_diagnostic_discrimination": diag_rate,
            "total_citations_evaluated": total_citations,
            "valid_direct_telemetry_citations": total_valid_telemetry,
            "historical_rag_analogies": total_historical_analogies,
            "missing_or_unresolved_citations": total_missing_unresolved,
        },
        "cases": case_results,
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results_payload, f, indent=2)
    print(f"Saved results to {out_file}")


if __name__ == "__main__":
    run_held_out_evaluation()
