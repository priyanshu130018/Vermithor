"""
End-to-End Verification of Vermithor Demo Workflow for INC-2026-1042
"""
import json
import os
import sys
import httpx
from datetime import datetime, timezone

# Add repo root and synthetic-incidents to sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO_ROOT)
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts", "demo", "synthetic-incidents"))

from backend.app.common.security import create_access_token

def run_demo_verification():
    base_url = os.getenv("VERMITHOR_API_URL", "http://localhost:8000")
    token = create_access_token(
        data={
            "sub": "demo-sre-verifier",
            "name": "Demo SRE Engineer",
            "org_id": "vermithor",
            "role": "admin",
        }
    )
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    print("=" * 70)
    print(" VERMITHOR END-TO-END DEMO VERIFICATION")
    print(" Incident: INC-2026-1042")
    print("=" * 70)

    # 1. Health Checks
    print("\n[Step 1] Verifying System & Agent Health Probes...")
    with httpx.Client(timeout=10.0) as http:
        health_res = http.get(f"{base_url}/health")
        print(f" - Gateway /health: HTTP {health_res.status_code} -> {health_res.json()}")
        assert health_res.status_code == 200

        agent_health = http.get(f"{base_url}/api/v1/agent/health", headers=headers)
        print(f" - Agent /agent/health: HTTP {agent_health.status_code} -> {agent_health.json()}")
        assert agent_health.status_code == 200
        assert agent_health.json().get("status") == "healthy"

    # 2. Trigger or Execute LangGraph Investigation Workflow
    print("\n[Step 2] Executing LangGraph Investigation Workflow via API...")
    inv_payload = {
        "incident_key": "INC-2026-1042",
        "lookback_minutes": 30,
        "allow_additional_queries": True,
        "max_additional_queries": 2,
        "force_refresh": True,
    }

    with httpx.Client(timeout=90.0) as http:
        inv_res = http.post(
            f"{base_url}/api/v1/agent/investigations",
            json=inv_payload,
            headers=headers,
        )
        print(f" - Investigation Trigger HTTP {inv_res.status_code}")
        if inv_res.status_code != 200:
            print(f"Error Response: {inv_res.text}")
            sys.exit(1)

        inv_data = inv_res.json()
        inv_key = inv_data.get("investigation_key")
        print(f" - Created/Retrieved Investigation: {inv_key}")
        print(f"   Status: {inv_data.get('status')}")
        print(f"   Target Service: {inv_data.get('target_service')}")
        print(f"   Confidence: {inv_data.get('confidence')}")
        print(f"   Leading Hypothesis: {inv_data.get('leading_hypothesis')}")
        print(f"   Model Provider: {inv_data.get('model_provider')}")
        print(f"   Is Fallback: {inv_data.get('is_fallback')}")

        report = inv_data.get("report") or {}
        print(f"\n[Step 3] Verifying Investigation Report Structure...")
        print(f" - Observed Facts Count: {len(report.get('observed_facts', []))}")
        for fact in report.get("observed_facts", [])[:3]:
            print(f"   * {fact}")
        print(f" - Hypotheses Evaluated Count: {len(report.get('hypotheses_evaluated', []))}")
        for hypo in report.get("hypotheses_evaluated", []):
            print(f"   * [{hypo.get('candidate_type')}] {hypo.get('hypothesis')}")
            print(f"     Status: {hypo.get('calibrated_status')} | Score: {hypo.get('original_score')} | Evidence IDs: {hypo.get('supporting_evidence_ids')}")
        
        evidence_items = report.get("evidence_items", [])
        print(f" - Evidence Citations Count: {len(evidence_items)}")
        for ev in evidence_items[:4]:
            print(f"   * [{ev.get('evidence_id')}] ({ev.get('source_type')}:{ev.get('source_id')}) {ev.get('claim')}")
            print(f"     Verification Status: {ev.get('verification_status')} (Verified: {ev.get('is_verified')})")

        rec_steps = report.get("recommended_diagnostic_steps", [])
        print(f" - Recommended Diagnostic Steps Count: {len(rec_steps)}")
        for step in rec_steps:
            print(f"   * [{step.get('priority')}] {step.get('action')} on {step.get('target_service')}")
            print(f"     Rationale: {step.get('rationale')}")
            print(f"     Requires Human Approval: {step.get('requires_human_approval')}")

        # Assert report contents requirements
        assert inv_data.get("leading_hypothesis") is not None
        assert len(evidence_items) > 0
        assert inv_data.get("confidence") > 0.0
        assert inv_data.get("target_service") == "payment-api"
        assert len(rec_steps) > 0

    # 4. Persistence & Retrieval Verification
    print("\n[Step 4] Verifying Investigation Persistence & Retrieval...")
    with httpx.Client(timeout=30.0) as http:
        # Fetch by incident key
        get_inc_res = http.get(
            f"{base_url}/api/v1/agent/investigations/incident/INC-2026-1042",
            headers=headers,
        )
        print(f" - GET /api/v1/agent/investigations/incident/INC-2026-1042: HTTP {get_inc_res.status_code}")
        assert get_inc_res.status_code == 200
        assert get_inc_res.json().get("investigation_key") == inv_key

        # Fetch by investigation key
        get_inv_res = http.get(
            f"{base_url}/api/v1/agent/investigations/{inv_key}",
            headers=headers,
        )
        print(f" - GET /api/v1/agent/investigations/{inv_key}: HTTP {get_inv_res.status_code}")
        assert get_inv_res.status_code == 200
        assert get_inv_res.json().get("investigation_key") == inv_key

        # List investigations
        list_res = http.get(
            f"{base_url}/api/v1/agent/investigations?incident_key=INC-2026-1042",
            headers=headers,
        )
        print(f" - GET /api/v1/agent/investigations: HTTP {list_res.status_code} (Total: {list_res.json().get('total')})")
        assert list_res.status_code == 200
        assert list_res.json().get("total") >= 1

    # 5. Code Repair Workflow & Human Gate Verification
    print("\n[Step 5] Triggering Safe Read-Only Code Repair Proposal...")
    repair_payload = {
        "investigation_key": inv_key,
        "repository_url": "backend/tests/fixtures/payment_service",
        "target_branch": "main",
        "force_refresh": True,
    }
    with httpx.Client(timeout=60.0) as http:
        rep_res = http.post(
            f"{base_url}/api/v1/agent/repairs",
            json=repair_payload,
            headers=headers,
        )
        print(f" - Repair Trigger HTTP {rep_res.status_code}")
        if rep_res.status_code != 200:
            print(f"Repair Error Response: {rep_res.text}")
            sys.exit(1)

        rep_data = rep_res.json()
        repair_key = rep_data.get("repair_key")
        print(f" - Repair Key: {repair_key}")
        print(f"   Status: {rep_data.get('status')}")
        print(f"   Validation Status: {rep_data.get('validation_status')}")
        print(f"   Approval Status: {rep_data.get('approval_status')}")
        print(f"   Requires Human Approval: {rep_data.get('requires_human_approval')}")
        print(f"   Is Read-Only Pilot: {rep_data.get('is_read_only_pilot')}")
        print(f"   Pilot Audit Notice: {rep_data.get('pilot_audit_notice')}")

        assert rep_data.get("requires_human_approval") is True
        assert rep_data.get("is_read_only_pilot") is True

        patch_hash = rep_data.get("patch_hash")
        print(f"   Patch Hash: {patch_hash}")
        proposed_patch = rep_data.get("proposed_patch") or ""
        print(f"   Proposed Patch Diff:\n{proposed_patch[:300]}...")

        # Test Human Approval Gate
        print("\n[Step 6] Testing Human Approval Gate (Non-Executing)...")
        app_payload = {
            "action": "APPROVE",
            "reviewer": "sre-operator-1",
            "notes": "Approved by Senior SRE in supervised pilot test session.",
            "expected_patch_hash": patch_hash,
        }
        app_res = http.post(
            f"{base_url}/api/v1/agent/repairs/{repair_key}/approve",
            json=app_payload,
            headers=headers,
        )
        print(f" - Human Approval Response HTTP {app_res.status_code}")
        assert app_res.status_code == 200
        app_data = app_res.json()
        print(f"   Approval Status: {app_data.get('approval_status')}")
        print(f"   Approved By: {app_data.get('approved_by')}")
        print(f"   PR URL: {app_data.get('pull_request_url')} (Should remain None / unpushed in read-only pilot)")
        print(f"   Read-Only Pilot Notice: {app_data.get('pilot_audit_notice')}")

        assert app_data.get("approval_status") == "APPROVED"
        assert app_data.get("pull_request_url") is None  # Never pushed to remote in read-only pilot

    # 6. Frontend Dev Server Check
    print("\n[Step 7] Checking Frontend Server & Incident Availability...")
    with httpx.Client(timeout=10.0) as http:
        fe_res = http.get("http://localhost:5173")
        print(f" - Frontend Root (http://localhost:5173): HTTP {fe_res.status_code}")
        assert fe_res.status_code == 200

        fe_inc_res = http.get("http://localhost:5173/incidents/INC-2026-1042")
        print(f" - Frontend Incident Route (/incidents/INC-2026-1042): HTTP {fe_inc_res.status_code}")
        assert fe_inc_res.status_code == 200

        # Also verify backend incident query that frontend uses
        be_inc = http.get(f"{base_url}/api/v1/incidents/INC-2026-1042", headers=headers)
        print(f" - Backend GET /api/v1/incidents/INC-2026-1042: HTTP {be_inc.status_code}")
        assert be_inc.status_code == 200

    print("\n" + "=" * 70)
    print(" ALL END-TO-END DEMO VERIFICATION STEPS PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    run_demo_verification()
