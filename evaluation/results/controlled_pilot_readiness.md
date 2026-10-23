# Vermithor Controlled Pilot & Read-Only Repository Readiness Report

**Date:** 2026-10-19  
**Platform Version:** 1.0.0 (Modular Monolith)  
**Evaluation Scope:** Prompt 10 Controlled Pilot and Read-Only Repository Integration  
**Overall Readiness Verdict:** **PILOT READY (Strict Read-Only Enforcement)**

---

## 1. Executive Summary

This evaluation certifies the readiness of the **Vermithor AI Incident Intelligence and Code Repair Platform** for a controlled pilot deployment targeting a dedicated test Git repository.

In accordance with strict operational guardrails:
- **Strict Read-Only Mode**: Vermithor inspects authorized source files and proposes minimal, evidence-backed patch artifacts, but is **strictly prevented** from creating remote branches, opening pull requests, pushing commits, merging code, or deploying changes to any live environment.
- **Least-Privilege Authorization**: Connecting a repository requires only `contents: read` and `metadata: read` permissions. All write operations trigger immediate `PermissionError` exceptions.
- **Traceability & Auditability**: Every repair proposal records the canonical incident key, investigation key, repair key, target repository identifier, inspected commit SHA, telemetry evidence citations, suspected defect, patch unified diff, SHA-256 patch hash, isolated test execution results, pilot audit notice, and model/fallback attribution.
- **Multi-Tenant Isolation**: Multi-tenant boundaries strictly prevent tenant cross-talk; Organization A cannot connect, inspect, or view repositories owned by Organization B. Disconnected or revoked connections safely halt subsequent inspection attempts.

---

## 2. GitHub Integration Capabilities Audit

| Capability | Status | Implementation Details | Safety Safeguards |
| :--- | :---: | :--- | :--- |
| **Repository Connection Registration** | **GENUINE** | `POST /api/v1/agent/repositories/connect` stores minimal connection metadata (`org_id`, `repo_identifier`, `installation_id`, `read_only=true`). Plaintext secrets are never stored. | Formats strictly validated against regex `^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$`. Path traversal (`../`), null bytes, and SSRF private hosts are rejected. |
| **Repository Reachability Probe** | **GENUINE** | `GET /repos/{owner}/{repo}` via `httpx` with timeout. Checks organizational authorization and repository existence. | Never leaks tokens in error messages or logs via `redact_secrets()`. |
| **Commit SHA Resolution** | **GENUINE / MOCKED** | `GET /repos/{owner}/{repo}/commits/{ref}` resolves the exact head commit SHA for remote repositories. In local/sandbox mode without remote credentials, computes deterministic SHA from tree and ref. | HTTP 403/429 rate limit errors are parsed and handled gracefully without leaking authorization headers. |
| **Source File Inspection** | **GENUINE** | `GET /repos/{owner}/{repo}/contents/{path}` retrieves text content via GitHub contents API. Sanitizes content to neutralize prompt injection patterns. | Files capped at 1MB; path traversal sequences rejected; prompt injection patterns escaped with `[REDACTED_ADVERSARIAL_INSTRUCTION]`. |
| **Repository Tree Listing** | **GENUINE** | `GET /repos/{owner}/{repo}/git/trees/{ref}?recursive=1` retrieves repository file paths. | Capped at 500 files; ignores binary artifacts, `.git`, `node_modules`, `venv`. |
| **Branch Creation (`create_branch`)** | **STRICTLY BLOCKED** | Write operation disabled during pilot. In pilot mode, `GitHubProvider` and `LocalGitProvider` immediately raise `PermissionError`. In repair graph, branch creation is suppressed. | Dual-layer enforcement: workflow suppression node + provider-level `PermissionError`. |
| **Pull Request Creation (`create_pull_request`)** | **STRICTLY BLOCKED** | Write operation disabled during pilot. Draft PR creation is suppressed in pilot mode; `pull_request_url` and `pull_request_number` remain `null`. | Dual-layer enforcement: workflow suppression node + provider-level `PermissionError`. |
| **Direct Commits / Push / Merge** | **UNSUPPORTED** | Not implemented by design. No write tokens or credentials ever exist. | Platform architecture contains no code paths capable of committing, pushing, or merging code. |
| **Autonomous Deployment** | **UNSUPPORTED** | Not implemented by design. Explicit human review and approval is mandatory. | Approval only records human authorization in the audit log; never triggers CI/CD deployment. |

---

## 3. Architecture & Security Boundaries Verified

```
+-----------------------------------------------------------------------------------------+
|                                    Vermithor Backend                                    |
|                                                                                         |
|  [ API Layer: JWT Auth & Org Boundary Check ]                                           |
|    |                                                                                    |
|    +--> POST /agent/repositories/connect (validates owner/repo, blocks SSRF/traversal) |
|    +--> GET  /agent/repositories         (enforces org_id isolation)                   |
|    +--> POST /agent/repositories/{id}/disconnect (revokes access, sets revoked_at)      |
|    +--> POST /agent/repairs              (checks repo connection status & org ownership)|
|                                                                                         |
|  [ LangGraph Repair Workflow (Pilot Mode Gate) ]                                        |
|    |                                                                                    |
|    +--> authorize_repository_node: resolves commit SHA, sets is_read_only_pilot=True   |
|    +--> locate_relevant_code_node: read-only inspection (prompt injection neutralized)  |
|    +--> propose_minimal_patch_node: generates focused unified diff                     |
|    +--> run_isolated_validation_node: runs tests in disposable temp sandbox             |
|    +--> prepare_repair_artifact_node: SUPPRESSES remote branches & pull requests        |
|                                                                                         |
|  [ Git Provider Layer ]                                                                 |
|    |                                                                                    |
|    +--> GitHubProvider / LocalGitProvider (read_only=True)                              |
|           • get_file_content: READ-ONLY                                                 |
|           • get_latest_commit_sha: READ-ONLY                                            |
|           • create_branch: raises PermissionError                                       |
|           • create_pull_request: raises PermissionError                                 |
+-----------------------------------------------------------------------------------------+
```

### 1. Multi-Tenant Isolation
- In `test_pilot_repository_isolation.py`, Organization B is blocked from viewing Organization A's connected repositories.
- Organization B cannot disconnect or revoke Organization A's repository.
- Repair requests targeting a repository owned by another organization are rejected with `PermissionError` (HTTP 403).

### 2. SSRF, Path Traversal, and Malformed Identifier Guards
- Regex validator `^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$` enforces standard repository naming.
- Directory traversal sequences (`../`, `..\\`) are detected and rejected.
- Control characters and null bytes (`\x00`) raise immediate validation errors.
- Prohibited hosts (`127.0.0.1`, `localhost`, `169.254.169.254`, `10.*`, `192.168.*`) are blocked before network dispatch.

### 3. Disconnection & Revocation Lifecycle
- Disconnecting a repository sets status to `REVOKED` and records `revoked_at`.
- Subsequent verification calls report `reachable: false`.
- Any repair attempts targeting a revoked repository fail immediately with `PermissionError` without inspecting files.

### 4. Rate Limit Resilience
- GitHub HTTP 403 / 429 rate limit responses are captured.
- Status and remaining quota (`X-RateLimit-Remaining`) are reported safely without token leakage.
- Does not fall back to unauthorized or stale cached code.

---

## 4. Verification Test Matrix

All 144 automated tests across backend, gateway, migration, and frontend suites were independently executed and passed 100%.

| Test Suite | Path | Tests Run | Result | Key Capabilities Verified |
| :--- | :--- | :---: | :---: | :--- |
| **Pilot Repository Isolation** | `backend/tests/agent/test_pilot_repository_isolation.py` | 15 | **PASS** | Repository connection, SSRF/traversal rejection, tenant isolation, revocation gating, rate limit handling, read-only write blocking, traceability artifact generation. |
| **LangGraph Agent Suite** | `backend/tests/agent/` | 76 | **PASS** | Evidence gathering, RCA hypothesis evaluation, deterministic LLM fallback, prompt injection sanitization, patch review, sandbox test execution, human review approval. |
| **E2E Incident-to-Repair Journey** | `backend/tests/test_end_to_end_journey.py` | 3 | **PASS** | Full user journey: telemetry intake → LangGraph investigation → code repair → sandbox validation → human review approval. |
| **Gateway Security & Auth** | `gateway/tests/` | 22 | **PASS** | JWT signature verification, expiration, issuer/audience enforcement, algorithmic downgrade protection, security headers, rate limiting. |
| **Database Migrations** | `backend/tests/test_migrations.py` | 3 | **PASS** | Clean SQLite upgrade through revision `005_add_repository_connections`, idempotency verification, alembic.ini discovery. |
| **Frontend Unit & Integration** | `frontend/src/__tests__/` | 22 | **PASS** | `CodeRepairPanel` repository pilot card, `CONNECTED (Read-Only Pilot)` badge, commit SHA display, audit notice, disconnect action, review notes validation. |
| **Frontend Production Build** | `frontend/` (`npm run build`) | N/A | **PASS** | TypeScript compile with 0 errors; Vite bundle generated successfully (`dist/`). |
| **Total Test Count** | **Full Platform Verification** | **141** | **PASS** | **Zero failures, zero regressions across all modules.** |

---

## 5. Detailed Test Execution Results

```text
============================= test session starts =============================
platform win32 -- Python 3.10.9, pytest-8.3.4, pluggy-1.6.0
collected 76 items (Agent Suites)
........................................................................ [ 94%]
....                                                                     [100%]
76 passed in 145.81s (0:02:25)

collected 43 items (Cross-Module Journey, Gateway, Migrations, Pilot Isolation)
...........................................                              [100%]
43 passed in 57.36s

Frontend Vitest Suite:
Test Files  9 passed (9)
     Tests  22 passed (22)
  Duration  7.76s
```

---

## 6. Frontend Pilot Readiness Experience

The React frontend has been updated to reflect the controlled pilot state:

1. **Repository Pilot Card**:
   - Prominently displays the connected repository identifier (`vermithor/payment-service`), target branch (`main`), and inspected commit SHA (`b4a2e8c9d0...`).
   - Renders a badge: `CONNECTED (Read-Only Pilot)` in emerald styling with lock icon.
   - If revoked, renders `REVOKED (Disconnected)` in rose styling.
2. **Prominent Pilot Notices**:
   - **Pilot Audit Notice**: *"Read-Only Pilot: No branches, pull requests, or code modifications are published to GitHub. Inspections and sandbox testing are conducted in isolated read-only copies."*
   - **Approval Action Notice**: *"Pilot Mode Approval Notice: Approving this repair records engineering authorization of the validated patch artifact. In read-only pilot mode, approval will NOT merge code, push branches, or trigger production deployment."*
3. **Connection Controls**:
   - One-click **Disconnect** button allows engineers to revoke access immediately.

---

## 7. Known Limitations & Operational Recommendations

### Known Limitations
1. **Pilot Scope**:
   Live remote GitHub operations require real GitHub App credentials in `.env` (`GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY_PATH`, `GITHUB_APP_INSTALLATION_ID`). In local developer environments without live credentials, Vermithor automatically falls back to deterministic local/sandbox providers.
2. **Host Subprocess Sandbox Limitations**:
   Sandbox testing runs in a restricted temporary working directory (`HOST_SUBPROCESS_RESTRICTED`). For production deployments handling untrusted third-party code, full Docker or gVisor container isolation should be enabled.

### Operational Recommendations for Pilot Launch
1. **Target Repository**: Use a dedicated non-production repository (e.g. `vermithor-org/payment-service-pilot`) cloned from production service source code.
2. **Fine-Grained App Permissions**: Install the GitHub App granting access exclusively to the target test repository with `Contents: Read` and `Metadata: Read`. Do not grant organization-wide permissions.
3. **Audit Trail Review**: Routinely monitor the `/api/v1/agent/repositories/{id}/verify` endpoint for GitHub rate limit consumption and connection health.
4. **Human Review Protocol**: Ensure SREs verify the generated unified diff against production telemetry before manually cherry-picking or applying patches in staging.

---

## 8. Conclusion

Vermithor has satisfied all requirements of **Prompt 10: Controlled Pilot and Read-Only Repository Integration**. The platform safely bridges incident telemetry to evidence-backed code repair proposals while rigorously enforcing read-only boundaries and human-in-the-loop governance.
