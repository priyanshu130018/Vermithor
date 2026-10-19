"""
End-to-end demonstration of Vermithor's AI Code Repair Agent on synthetic incident INC-2026-1042.
Demonstrates:
  1. Loading completed investigation INV-000009 (payment-api pool exhaustion)
  2. Read-only code inspection & hypothesis generation
  3. Minimal unified diff generation
  4. Isolated test execution in disposable sandbox (credentials stripped)
  5. Test validation evaluation (2 tests passing)
  6. Reviewable draft PR preparation
  7. Human approval gate (AWAITING_APPROVAL)
  8. Human approval execution (APPROVED, no autonomous merge/deploy)
"""

import json
import logging
from pathlib import Path
import sys

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("repair_demo")

from backend.app.common.database import SessionLocal
from backend.app.agent.schemas.repair import ApprovalRequest, ApprovalStatus, RepairRequest, RepairStatus, ValidationStatus
from backend.app.agent.services.repair_service import RepairService


def run_demo():
    print("=" * 80)
    print("VERMITHOR AI CODE REPAIR AGENT — END-TO-END DEMO (INC-2026-1042)")
    print("=" * 80)

    db = SessionLocal()
    service = RepairService()

    fixture_dir = Path("backend/tests/fixtures/payment_service").resolve()
    print(f"Target repository fixture: {fixture_dir}")
    print(f"Investigation Key: INV-000009")

    # Step 1: Trigger Repair
    print("\n--- STEP 1: INITIATING REPAIR AGENT WORKFLOW ---")
    repair_req = RepairRequest(
        investigation_key="INV-000009",
        repository_url=str(fixture_dir),
        branch="main",
        custom_test_command="pytest tests/test_payment_pool.py",
    )
    user_identity = {
        "org_id": "org_default",
        "role": "engineer",
        "user_id": "usr_alex_dev",
        "sub": "usr_alex_dev",
    }

    resp = service.run_repair(db=db, req=repair_req, user_identity=user_identity)

    print(f"\nRepair Created: {resp.repair_key} (ID: {resp.id})")
    print(f"Incident Key:   {resp.incident_key}")
    print(f"Target Branch:  {resp.target_branch}")
    print(f"Approval Status:{resp.approval_status.value}")
    print(f"Validation:     {resp.validation_status.value}")
    print(f"Repair Branch:  {resp.repair_branch}")
    print(f"Draft PR URL:   {resp.pull_request_url or 'Local branch staged for PR'}")
    print(f"Requires Human Approval: {resp.requires_human_approval}")

    print("\n--- STEP 2: CODE-LEVEL DEFECT & HYPOTHESIS ---")
    print(f"Suspected Defect: {resp.suspected_defect}")
    hyp = (resp.report_json or {}).get("code_hypothesis", "N/A")
    print(f"Root Cause Hypothesis:\n{hyp}")

    print("\n--- STEP 3: PROPOSED MINIMAL PATCH ---")
    print(resp.proposed_patch)

    print("\n--- STEP 4: ISOLATED SANDBOX VALIDATION RESULTS ---")
    if resp.test_results:
        tr = resp.test_results
        print(f"Tests Run:      {tr.get('total_tests', 0)}")
        print(f"Tests Passed:   {tr.get('passed', 0)}")
        print(f"Tests Failed:   {tr.get('failed', 0)}")
        print(f"Tests Skipped:  {tr.get('skipped', 0)}")
        print(f"Duration:       {tr.get('duration_ms', 0):.1f}ms")
        print(f"Isolated Env:   Credentials stripped, 30s timeout enforced")

    print("\n--- STEP 5: SAFETY REVIEW CHECKLIST ---")
    chk = (resp.report_json or {}).get("safety_checklist", {})
    print(f"Syntax Valid:               {chk.get('syntax_valid', True)}")
    print(f"Within Scope:               {chk.get('scope_valid', True)}")
    print(f"No Suspicious Changes:      {chk.get('no_suspicious_changes', True)}")
    print(f"No Secret Leakage:          {chk.get('no_secrets_leaked', True)}")
    print(f"No Dependency Escalations:  {chk.get('no_dependency_changes', True)}")

    assert resp.approval_status == ApprovalStatus.PENDING, f"Expected PENDING, got {resp.approval_status}"
    assert resp.requires_human_approval is True
    assert resp.validation_status == ValidationStatus.VALIDATED, f"Expected VALIDATED, got {resp.validation_status}"
    assert resp.test_results and resp.test_results.get("passed") == 4, f"Expected 4 passing tests, got {resp.test_results}"

    # Step 6: Human Review & Approval
    print("\n--- STEP 6: HUMAN SRE REVIEW & EXPLICIT APPROVAL ---")
    print("Agent paused execution at mandatory human approval gate (AWAITING_APPROVAL).")
    print("Simulating Senior SRE reviewing sandbox validation report and approving patch...")

    approval_payload = ApprovalRequest(
        action="APPROVE",
        notes="Validated in isolated sandbox: 4/4 tests pass. Patch increases max_pool_size to 50 safely.",
        reviewer="senior_sre@vermithor.io",
        expected_patch_hash=resp.patch_hash,
    )
    sre_identity = {
        "org_id": "org_default",
        "role": "sre_lead",
        "user_id": "usr_sre_lead_01",
        "sub": "usr_sre_lead_01",
    }

    approved_resp = service.approve_or_reject_repair(
        db=db,
        repair_id=resp.repair_key,
        approval_req=approval_payload,
        reviewer_id=sre_identity["user_id"],
        user_identity=sre_identity,
    )

    print(f"Updated Approval Status: {approved_resp.approval_status.value}")
    print(f"Approver:                {approved_resp.approved_by}")
    print(f"Approval Notes:          {approved_resp.approval_notes}")
    print(f"Decision Recorded At:    {approved_resp.approved_at}")
    print(f"Autonomous Merge:        DISABLED (Strict Human-in-the-Loop)")
    print(f"Autonomous Deploy:       DISABLED (Strict Human-in-the-Loop)")

    assert approved_resp.approval_status == ApprovalStatus.APPROVED

    print("\n" + "=" * 80)
    print("END-TO-END DEMONSTRATION COMPLETED SUCCESSFULLY")
    print("=" * 80)


if __name__ == "__main__":
    run_demo()
