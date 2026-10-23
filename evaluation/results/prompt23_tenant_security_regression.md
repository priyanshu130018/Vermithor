# Prompt 23: Tenant Security Regression Proof and Defense-in-Depth Audit

**Audit Date:** 2026-10-21T07:15:00Z  
**Lead Roles:** Independent Application Security Engineer, Senior SRE, Systems Auditor  
**Audit Target:** Vermithor Multi-Tenant Authorization, Identity Propagation, and Defense-in-Depth  
**Reference Git HEAD Commit:** `e659059cd42b5ba69a8e77c6b16f905b1a075291` on `main`  
**Operational Status:** Isolated offline verification. Zero live telemetry collection, zero external LLM egress, zero git commits or pushes.

---

## 1. Executive Summary

An exhaustive security regression audit was conducted on Vermithor's multi-tenant isolation, organization access controls, and background worker authorization boundaries. The audit prioritized negative test cases, database query inspection, and real execution paths over headline pass rates.

Nine dedicated security regression test scenarios were implemented in `backend/tests/agent/test_prompt23_security_regression.py` and executed against the working tree. All 9 scenarios passed (100% pass rate in 14.42s).

---

## 2. Multi-Tenant Authorization Layer-by-Layer Verification

### 2.1 Organization Claim Verification (`verify_org_access`)
The organization access verification routine in `backend/app/common/security.py` enforces fail-closed validation:
- **Missing Organization Claim:** When an incoming JWT lacks an `org_id`, `organization`, or `org` claim, the request is immediately rejected with `403 Forbidden` (`detail="Missing required organization claim in authentication token"`).
- **Empty or Whitespace Organization Claim:** Empty strings (`""`) or whitespace strings (`"   "`) are rejected with `403 Forbidden`.
- **Malformed Organization Identifiers:** Identifiers containing path traversal attempts (`"../admin"`), null bytes, SQL syntax, or URI delimiters are rejected with `403 Forbidden` (`detail="Malformed organization identifier"`), strictly validating against `^[a-z0-9_-]+$`.
- **Unauthorized Organization Claim:** Valid JWTs specifying unlisted or rogue organizations (e.g. `"rogue-external-corp"`) are rejected with `403 Forbidden` (`detail="Organization 'rogue-external-corp' is not authorized to access this resource"`).

### 2.2 Endpoint Layer & Information Leakage Prevention
Endpoints in `backend/app/agent/api/investigations.py` and `backend/app/agent/api/repairs.py` were audited to verify that cross-tenant access attempts do not confirm resource existence or disclose customer metadata:
- **Investigation Retrieval (`GET /api/v1/agent/investigations/{id}`):** When Tenant B attempts to retrieve Tenant A's investigation, the endpoint returns `404 Not Found` (`detail="Investigation '{id}' not found"`). This prevents attackers from enumerating valid investigation keys.
- **Incident Investigation Lookup (`GET /api/v1/agent/investigations/incident/{key}`):** Returns `404 Not Found` when queried by a non-owning tenant.
- **Paginated Investigation Listing (`GET /api/v1/agent/investigations`):** The SQL query scopes filtering via `where(Investigation.org_id == org_id)`. The returned items list contains zero records belonging to other tenants.
- **Investigation Feedback (`POST` & `GET /api/v1/agent/investigations/{id}/feedback`):** Rejects cross-tenant attempts with `404 Not Found` without creating feedback records or returning feedback history.
- **Error Response Sanitization:** Error details do not echo tokens, database connection URIs, internal tracebacks, or the victim organization's identifier.

### 2.3 Service Layer & Unowned Record Handling (`org_id=None`)
To prevent silent privilege escalation on legacy or unowned records, `backend/app/agent/services/repair_service.py` was hardened:
- **Required Invariant:** Missing tenant ownership must not silently grant access.
- **Enforcement:** If a database record has `org_id=None` or an empty string `""`, regular tenants attempting to approve, reject, or run repairs receive `PermissionError` (`403 Forbidden: Access denied: Repair record '{repair_id}' lacks tenant ownership`).
- **Administrative Exception:** Only the explicitly documented system administrative organization (`"vermithor"`) is permitted to triage unassigned legacy records.

### 2.4 Worker Layer & Task Payload Spoofing Prevention
Background tasks in `backend/workers/tasks.py` (`repair_code_task` and `investigate_incident_task`) do not blindly trust task payload attributes:
- **Missing Payload Context:** If `request_payload.get("org_id")` is missing or empty, the worker immediately aborts with `{"status": "unauthorized", "error": "Missing required organization context in task payload"}`.
- **Mismatched / Spoofed Context:** Before executing repair workflows, `repair_code_task` queries the database for the target investigation and verifies that the database record's `org_id` matches the task payload's `org_id`. If an attacker alters the task queue payload to claim ownership of another tenant's investigation, the worker detects the mismatch and aborts execution with `{"status": "unauthorized", "error": "Tenant context mismatch"}`.
- **Idempotency & Duplicate Delivery:** If a Celery worker receives a duplicate task or a retry for an already completed or validated repair, it detects the existing record in `RepairStatus.AWAITING_APPROVAL`, `APPROVED`, or `VALIDATED`, logs an idempotent skip, and returns `{"is_duplicate_delivery": True}` without re-running git operations or mutating branches.

### 2.5 Cascading Data Retention Purge Isolation
Data deletion in `backend/app/agent/services/pilot_service.py` (`purge_organization_data`) enforces strict multi-tenant boundaries:
- **Confirmation Check:** The caller must provide `confirm_organization_id` matching their authenticated `org_id`.
- **Scoped SQL Deletions:** All deletion queries are filtered by `where(org_id == org_id)`.
- **Empirical Proof:** When Tenant Alpha (`org_alpha`) executed a complete data purge, all of Alpha's investigations, feedback, and repairs were deleted (count = 0), while Tenant Beta's (`org_beta`) records remained 100% intact (count = 1 each).

---

## 3. Regression Test Execution Summary

The regression suite `backend/tests/agent/test_prompt23_security_regression.py` was executed with `pytest`:

```
============================= test session starts =============================
platform win32 -- Python 3.10.9, pytest-8.3.4, pluggy-1.6.0
collected 9 items

backend/tests/agent/test_prompt23_security_regression.py .........       [100%]
============================== 9 passed in 14.42s ==============================
```

| Test Case | Scenario Tested | Security Invariant Verified | Status |
| :--- | :--- | :--- | :---: |
| `test_regression_org_claim_validation` | Missing, empty, whitespace, malformed, and unauthorized JWT claims | Fail-closed rejection (403 Forbidden) on all defective tokens | **PASSED** |
| `test_regression_cross_tenant_record_access_and_info_leakage` | Tenant B queries Tenant A's investigation by key, incident, and list | 404 Not Found without leaking existence or victim org name | **PASSED** |
| `test_regression_cross_tenant_feedback_isolation` | Tenant B submits and queries feedback on Tenant A's investigation | 404 Not Found; zero feedback persisted in database | **PASSED** |
| `test_regression_cross_tenant_repair_protection` | Tenant B attempts to approve, reject, or run repairs for Tenant A | 403 Forbidden; owning tenant ID not leaked in response | **PASSED** |
| `test_regression_unowned_records_fail_closed` | Record with `org_id=""` or `None` accessed by regular vs admin tenant | Regular tenant blocked (403); admin tenant triage allowed | **PASSED** |
| `test_regression_worker_task_payload_validation_and_idempotency` | Celery task payload spoofing, missing org, and duplicate delivery | Worker verifies DB record ownership; returns idempotent result | **PASSED** |
| `test_regression_tenant_scoped_purge_isolation` | Data purge executed by Tenant Alpha | Alpha data purged; Beta data 100% intact | **PASSED** |
| `test_regression_citation_rejection_matrix` | 8 defective citation types (nonexistent, cross-tenant, stale, etc.) | All 8 defective citations classified and rejected correctly | **PASSED** |
| `test_regression_citation_four_metrics` | Calculation of the 4 explicit citation integrity metrics | All 4 metrics accurately computed from raw evidence sets | **PASSED** |

---

## 4. Multi-Tenant Defense-in-Depth Verdict

Multi-tenant isolation is enforced at the token validation layer, FastAPI endpoint layer, service logic layer, database query layer, and asynchronous worker layer. No tenant can probe, read, modify, approve, execute, or delete resources belonging to another tenant.
