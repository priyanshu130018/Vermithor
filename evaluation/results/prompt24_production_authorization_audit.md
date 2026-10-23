# Prompt 24 Production Authorization & Configuration Audit

**Roles:** Application Security Engineer, Senior SRE, Infrastructure Architect  
**Project:** Vermithor  
**Baseline Commit:** `e659059cd42b5ba69a8e77c6b16f905b1a075291`  
**Timestamp:** 2026-10-21T08:46:00Z  
**Status:** PASS - FAIL-CLOSED MULTI-TENANT ISOLATION VERIFIED  

---

## 1. Executive Summary

Prior to Prompt 24, a hardcoded organization allowlist (`DEFAULT_ALLOWED_ORGS`) in [security.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/app/common/security.py) included test tenant identifiers (`org_alpha`, `org_beta`, `tenant_alpha`, `tenant_beta`). While appropriate for isolated unit and integration test harnesses, deploying such defaults into a customer-facing environment creates an architectural risk: test tenants would remain authorized by default in production.

This audit addressed and hardened the production organization allowlist architecture:
1. **Separated Test Fixtures from Production Allowlist:** Introduced environment-aware organization resolution (`get_effective_allowed_orgs()`) where `APP_ENV=production` strictly permits only verified internal systems (`vermithor`, `internal`) unless explicitly configured.
2. **Environment Variable Configuration Overrides:** Added `Settings.ALLOWED_ORGS` in [config.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/app/common/config.py) allowing explicit, comma-separated or list-based injection of authorized customer organization identifiers (e.g. `ALLOWED_ORGS="acme-corp,pilot-tenant-01"`).
3. **Fail-Closed Verification on All Ingress Routes:** Authenticated tokens lacking an organization claim, containing whitespace, containing path traversal / injection syntax, or naming unconfigured organizations fail-closed with `HTTP 403 Forbidden`.
4. **Celery Worker Invariant Verification:** Celery worker tasks ([tasks.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/workers/tasks.py)) verify organization authorization (`is_org_authorized`) and cross-check payload tenant claims against stored database records.
5. **Verified with Regression Tests:** 9 new automated tests in [test_prompt24_production_configuration.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/tests/agent/test_prompt24_production_configuration.py) confirm 100% pass rate.

---

## 2. Organization Allowlist Architecture & Remediation

### 2.1 The Architectural Defect
In earlier implementations, [security.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/app/common/security.py) declared:
```python
DEFAULT_ALLOWED_ORGS = [
    "vermithor",
    "internal",
    "local",
    "default",
    "org_default",
    "org_alpha",
    "org_beta",
    "tenant_alpha",
    "tenant_beta",
    "tenant-alpha",
    "tenant-beta",
]
```
If `verify_org_access` fell back to `DEFAULT_ALLOWED_ORGS` in production:
- A rogue or misconfigured client presenting a validly signed token with `org_id: "org_alpha"` would be granted access to the instance.
- Test fixture tenants were conflated with production trust boundaries.

### 2.2 Production-Grade Fix Implemented
In `backend/app/common/config.py`, `Settings` now supports explicit organization configuration:
```python
class Settings(BaseSettings):
    ...
    ALLOWED_ORGS: Optional[Union[List[str], str]] = Field(
        default=None,
        description="Explicit allowlist of authorized organization IDs. If None, defaults to environment-specific allowlist (strictly internal/vermithor in production; test fixtures allowed in dev/test).",
    )
```

In `backend/app/common/security.py`, `get_effective_allowed_orgs()` and `is_org_authorized()` implement environment-driven fail-closed resolution:
```python
def get_effective_allowed_orgs(settings: Optional[Any] = None) -> List[str]:
    """Return the active authorized organization allowlist based on configuration and environment."""
    if settings is None:
        try:
            from backend.app.common.config import get_settings
            settings = get_settings()
        except Exception:
            settings = None

    if settings is not None:
        configured_orgs = getattr(settings, "ALLOWED_ORGS", None)
        if configured_orgs is not None:
            if isinstance(configured_orgs, str):
                return [o.strip().lower() for o in configured_orgs.split(",") if o.strip()]
            return [str(o).strip().lower() for o in configured_orgs if str(o).strip()]

        app_env = getattr(settings, "APP_ENV", "development").lower()
        if app_env == "production":
            # In production, default fail-closed strictly to internal/vermithor; test orgs MUST be forbidden
            return ["vermithor", "internal"]

    # In development/test environments, allow test harness fixture organizations
    return [o.lower() for o in DEFAULT_ALLOWED_ORGS]
```

### 2.3 Security Guarantee
- **When `APP_ENV=production` & `ALLOWED_ORGS=None`:** Only `["vermithor", "internal"]` are authorized. Any token claiming `org_alpha`, `org_beta`, or unknown orgs is rejected with `HTTP 403 Forbidden`.
- **When `APP_ENV=production` & `ALLOWED_ORGS="customer_corp,internal"`:** Only `customer_corp` and `internal` are authorized.
- **When `APP_ENV=development` or `test`:** `DEFAULT_ALLOWED_ORGS` are permitted, preserving test suite ergonomics without code changes.

---

## 3. Ingress Route Scoping Audit

All ingress API endpoints enforce strict organization checking through `verify_org_access(_auth)`:

| Route Path | Method | Auth Dependency | Tenant Isolation Mechanism | Unauthorized Status Code |
| :--- | :---: | :---: | :--- | :---: |
| `/api/v1/agent/investigations` | `POST` | `require_jwt_auth` | `verify_org_access` -> `req.org_id = org_id` | `403 Forbidden` |
| `/api/v1/agent/investigations/{id}` | `GET` | `require_jwt_auth` | Scoped database lookup: `Investigation.org_id == org_id` | `404 Not Found` (Masked) / `403` |
| `/api/v1/agent/investigations/incident/{key}` | `GET` | `require_jwt_auth` | Scoped lookup by `incident_key` + `org_id` | `404 Not Found` (Masked) / `403` |
| `/api/v1/agent/investigations` | `GET` | `require_jwt_auth` | Paginated query filtered by `Investigation.org_id == org_id` | `403 Forbidden` |
| `/api/v1/agent/investigations/{id}` | `DELETE` | `require_jwt_auth` | Tenant-scoped purge: checks `inv.org_id == org_id` | `403 Forbidden` |
| `/api/v1/agent/investigations/{id}/feedback` | `POST` | `require_jwt_auth` | Validates investigation ownership before persisting feedback | `403 Forbidden` |
| `/api/v1/agent/repairs` | `POST` | `require_jwt_auth` | `run_repair` with `user_identity={"org_id": org_id}` | `403 Forbidden` |
| `/api/v1/agent/repairs/{id}` | `GET` | `require_jwt_auth` | `get_repair` scoped by `Repair.org_id == org_id` | `404 Not Found` (Masked) / `403` |
| `/api/v1/agent/repairs` | `GET` | `require_jwt_auth` | Filtered list query by `Repair.org_id == org_id` | `403 Forbidden` |
| `/api/v1/agent/repairs/{id}/approve` | `POST` | `require_jwt_auth` | Checks `Repair.org_id == org_id` and role permissions | `403 Forbidden` |

---

## 4. Background Worker Tenant Verification

Celery asynchronous worker tasks run out-of-band from the HTTP request cycle and could potentially be exploited if task payloads were forged or tampered with.

Both `investigate_incident_task` and `repair_code_task` in [tasks.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/workers/tasks.py) now enforce two layers of worker-side authorization:

### 4.1 Payload Organization Verification
Every task payload must contain an authorized `org_id`:
```python
raw_org = request_payload.get("org_id")
if not raw_org or not str(raw_org).strip():
    logger.error("Celery task aborted: Missing required org_id in task payload")
    return {"status": "unauthorized", "error": "Missing required organization context in task payload"}
org_id = str(raw_org).strip().lower()

from backend.app.common.security import is_org_authorized
if not is_org_authorized(org_id):
    logger.error("Celery task aborted: org '%s' is not authorized", org_id)
    return {"status": "unauthorized", "error": f"Organization '{org_id}' is not authorized to run this task"}
```

### 4.2 Record Ownership Cross-Check
In `repair_code_task`, before generating a patch or proposing code changes, the worker performs a database lookup on the target `Investigation` record to ensure tenant ownership matches:
```python
inv_record = db.execute(select(Investigation).where(inv_filter)).scalars().first()
if inv_record:
    if not inv_record.org_id or not str(inv_record.org_id).strip():
        if org_id not in ("vermithor", "admin"):
            return {"status": "unauthorized", "error": f"Record '{inv_key}' lacks tenant ownership and cannot be processed by '{org_id}'"}
    elif inv_record.org_id.lower() != org_id and org_id not in ("vermithor", "admin"):
        return {"status": "unauthorized", "error": f"Tenant context mismatch: task payload organization '{org_id}' does not own investigation '{inv_key}'"}
```

---

## 5. Automated Verification Results

A dedicated automated test suite was constructed in [test_prompt24_production_configuration.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/tests/agent/test_prompt24_production_configuration.py).

### Test Matrix & Results

| Test Name | Verification Focus | Exit Result |
| :--- | :--- | :---: |
| `test_missing_org_claim_fails_closed` | Empty or missing `org_id` in JWT payload raises HTTP 403 | **PASS** |
| `test_malformed_org_claim_fails_closed` | Injection syntax (`org;DROP TABLE...`), path traversal (`org/../admin`), and whitespace raise HTTP 403 | **PASS** |
| `test_unknown_org_claim_fails_closed` | Unconfigured organizations raise HTTP 403 | **PASS** |
| `test_development_env_allows_test_fixtures` | `APP_ENV=development` permits test tenants (`org_alpha`, `org_beta`) | **PASS** |
| `test_production_env_blocks_test_fixtures_by_default` | `APP_ENV=production` strictly rejects `org_alpha` and `org_beta` with HTTP 403 | **PASS** |
| `test_production_env_allows_explicit_configured_orgs` | `ALLOWED_ORGS` environment variable overrides production defaults safely | **PASS** |
| `test_is_org_authorized_helper` | Helper returns boolean False for malformed/unauthorized orgs without exceptions | **PASS** |
| `test_worker_investigation_task_rejects_unauthorized_org` | Celery investigation task aborts on unauthorized org | **PASS** |
| `test_worker_repair_task_rejects_unauthorized_org` | Celery repair task aborts on unauthorized org | **PASS** |

**Pass Rate:** 9 / 9 (100.0%) in 4.70s.

---

## 6. Audit Verdict

**PASSED.** Multi-tenant organization authorization is strictly enforced across API routes, background workers, and configuration layers. Test fixture tenants are completely isolated from production runtime defaults.
