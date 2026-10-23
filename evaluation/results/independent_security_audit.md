# Vermithor Pre-Pilot Independent Security Audit & Gate Verification Report

**Auditor:** Principal Application Security Engineer, Senior SRE, & SaaS Reliability Auditor  
**Audit Target:** Vermithor AI Incident Investigation & Supervised Pilot Architecture  
**Document Date:** October 20, 2026  
**Git Baseline Commit:** `e659059cd42b5ba69a8e77c6b16f905b1a075291`  
**Working Tree Status:** Preserved (All uncommitted files retained; zero destructive resets)  
**Final Audit Verdict:** **CONDITIONAL GO — SUPERVISED READ-ONLY REPLAY MODE ONLY**

---

## 1. Executive Summary & Audit Mandate

In accordance with Prompt 16, an adversarial, independent security and reliability audit was conducted on Vermithor prior to its first supervised customer pilot.

The previous readiness report recommended:
> **CONDITIONAL GO: supervised, read-only pilot in sanitized postmortem replay mode.**

Rather than accepting the prior report's conclusions, this audit independently inspected all source code, database migrations, network transport mechanisms, Celery worker task queues, and evaluation benchmarks. Disposable fixtures and mocked environments were utilized throughout; no real customer infrastructure was probed.

### Key Audit Findings & Remediations Overview

```
┌───────────────────────────────────────────────────────────────────────────────────────────────────┐
│                               INDEPENDENT SECURITY AUDIT SCORECARD                                │
├───────┬────────────────────────────────────────┬──────────┬─────────────┬─────────────────────────┤
│ ID    │ Verification Gate                      │ Severity │ Status      │ Remediation Summary     │
├───────┼────────────────────────────────────────┼──────────┼─────────────┼─────────────────────────┤
│ SEC-01│ Multi-Tenant Cascading Purge Flaw      │ CRITICAL │ REMEDIATED  │ Added org_id to models  │
│       │                                        │          │             │ & scoped purge logic    │
│ SEC-02│ TOCTOU DNS Rebinding & Evasive IPs     │ HIGH     │ REMEDIATED  │ Socket peer IP pinning  │
│       │                                        │          │             │ & IP format unwrapping  │
│ SEC-03│ Sensitive Credential & PII Redaction   │ HIGH     │ REMEDIATED  │ Enhanced regex covering │
│       │                                        │          │             │ JWT, URI creds & emails │
│ SEC-04│ Worker Task Kill-Switch Bypass         │ MEDIUM   │ REMEDIATED  │ Enforced pause check in │
│       │                                        │          │             │ Celery worker entrypoint│
│ SEC-05│ Read-Only Git & Infrastructure Bounds  │ LOW/NONE │ VERIFIED    │ Server-side read-only   │
│       │                                        │          │             │ invariants confirmed    │
│ SEC-06│ Benchmark Rigor & Provenance Grounding │ LOW/NONE │ VERIFIED    │ Zero live incidents     │
│       │                                        │          │             │ honestly disclosed      │
└───────┴────────────────────────────────────────┴──────────┴─────────────┴─────────────────────────┘
```

Following our remediations, **55 automated backend tests** and **24 frontend integration tests** are passing cleanly with zero errors.

---

## 2. Repository Baseline & Execution Discipline

1. **Commit Baseline:** `e659059cd42b5ba69a8e77c6b16f905b1a075291`.
2. **Working-Tree Integrity:** All existing changes (40 modified files, 54 untracked files) were preserved intact. No `git reset --hard` or uncommitted file discard occurred.
3. **No External Probing:** Zero outbound network requests were made to real customer systems, cloud metadata services, or external targets. All network tests used loopback servers (`127.0.0.1`) and mocked transports.
4. **Isolated Test Fixtures:** All adversarial tests executed against in-memory SQLite instances (`sqlite:///:memory:`) using `StaticPool`.

---

## 3. Tenant Isolation & Authorization Boundary Findings

### 3.1 Initial Vulnerabilities Discovered

1. **Missing Organization Column on Core Entities (CRITICAL):**
   - In `backend/app/agent/db/models.py`, `Investigation` and `Repair` tables lacked an `org_id` column.
   - Lookups in `get_investigation` and `get_repair` accepted an identifier (e.g. `INV-000001` or `REP-000001`) and returned the record regardless of the caller's authenticated organization claim.
2. **Global Cascading Data Deletion (CRITICAL):**
   - In `backend/app/agent/services/pilot_service.py` (`purge_organization_data`), when `incident_key` was not specified (i.e. full organization pilot purge), `delete(Repair)` and `delete(Investigation)` were executed without any `WHERE` clause.
   - In a shared multi-tenant database, Tenant A calling the purge endpoint wiped all investigations and code repairs across all tenants.
   - Furthermore, `delete(MetricObservation)` and `delete(Event)` were executed unconditionally, clearing the shared observability tables.

### 3.2 Remediation & Verification

1. **Alembic Schema Migration `008_add_org_id_to_investigations_and_repairs.py`:**
   - Added indexed `org_id: String(64)` column with default `"vermithor"` to both `investigations` and `repairs`.
   - Verified clean upgrade and idempotency via `backend/tests/test_migrations.py`.
2. **Scoped Retention Purge:**
   - Constrained `Investigation`, `Repair`, and `InvestigationFeedback` deletions strictly to `org_id`.
   - Replaced global deletion of `MetricObservation` and `Event` with service-scoped deletion: only observations and events belonging to the target organization's verified services are purged.
   - Purged Redis keys matching `*{org_id}*`.
3. **Horizontal Privilege Escalation Defense:**
   - Updated `GET /agent/investigations/{id}` and `GET /agent/repairs/{id}` to filter on `org_id == caller_org`.
   - Updated `POST /agent/repairs/{id}/approve` to reject cross-tenant approval with `HTTP 403 FORBIDDEN`.
4. **Adversarial Negative Tests (`test_adversarial_security_audit.py`):**
   - `test_cross_tenant_purge_isolation`: Tenant A purges all data; Tenant B records remain 100% intact.
   - `test_cross_tenant_targeted_incident_purge_isolation`: Tenant A requests deletion of Tenant B's incident key; 0 rows deleted.
   - `test_cross_tenant_investigation_read_blocked`: Cross-tenant read rejected with `HTTP 404`.
   - `test_cross_tenant_repair_read_and_approval_blocked`: Cross-tenant repair approval rejected.

---

## 4. SSRF, DNS Rebinding, & Outbound HTTP Hardening Findings

### 4.1 Initial Vulnerabilities Discovered

1. **Time-of-Check to Time-of-Use (TOCTOU) DNS Rebinding (HIGH):**
   - `SafeTelemetryHttpClient.execute_query` resolved the hostname via `socket.getaddrinfo` in `validate_telemetry_endpoint`.
   - However, it then passed the original URL string to `httpx.Client.request()`.
   - When `httpx` connected, it performed its own DNS lookup. An attacker could configure a DNS server with TTL=0 that returns a benign IP on the first lookup and `169.254.169.254` or `127.0.0.1` on the second lookup.
2. **Alternative IP Representations (HIGH):**
   - IPv4-mapped IPv6 addresses (`::ffff:169.254.169.254`, `[::ffff:127.0.0.1]`) have `is_loopback=False` and `is_link_local=False` in Python's `ipaddress` library unless explicitly unwrapped via `ip.ipv4_mapped`.
   - Decimal integer IP representations (e.g. `http://2852039166/`), hex representations (`0xa9fea9fe`), and octal notations (`0177.0.0.1`) bypassed string regex comparisons.

### 4.2 Remediation & Verification

1. **Socket-Level Peer Address Pinning:**
   - Implemented `SSRFProtectedSyncBackend(httpcore.SyncBackend)` and `SSRFSafeTransport(httpx.HTTPTransport)`.
   - Upon TCP connection establishment in `connect_tcp`, the backend inspects the physical connected peer socket:
     ```python
     peer_ip_str = sock.getpeername()[0]
     ip_obj = ipaddress.ip_address(peer_ip_str)
     _verify_ip_safety(ip_obj, allow_localhost=self.allow_localhost, allow_private=self.allow_private)
     ```
   - If the connected peer is cloud metadata (`169.254.169.254`), loopback (`127.0.0.1`), link-local, or private, the backend closes the socket immediately and raises `ValueError`. Not a single HTTP request byte is sent to the prohibited peer.
2. **Evasive IP Representation Parsing:**
   - Added `parse_ip_representation` in `backend/app/observability/security/safe_client.py` to normalize:
     - IPv4-mapped IPv6 (`::ffff:169.254.169.254` $\to$ `169.254.169.254`).
     - 32-bit integers (`2852039166` $\to$ `169.254.169.254`).
     - Hexadecimal (`0xa9fea9fe` $\to$ `169.254.169.254`).
     - Octal dotted notation (`0177.0.0.1` $\to$ `127.0.0.1`).
3. **HTTP Redirect & Response Size Limits:**
   - Configured `follow_redirects=False` in `SafeTelemetryHttpClient`. Any 301/302 response is rejected without following.
   - Enforced strict 2 MB response limits via `Content-Length` checks and streamed chunk limits.
4. **Adversarial Negative Tests (`test_adversarial_security_audit.py`):**
   - `test_dns_rebinding_socket_interception`: Proved socket peer validation terminates connection.
   - `test_cloud_metadata_endpoints_blocked`: Proved standard metadata hosts are blocked.
   - `test_alternative_ip_representations_and_userinfo_blocked`: Proved evasive encodings and userinfo are blocked.
   - `test_redirect_to_prohibited_destination_rejected`: Proved redirects are strictly rejected.
   - `test_response_streaming_size_limit_enforced`: Proved oversized responses return `HTTP 413`.

---

## 5. Secret Redaction, Lifecycle Handling & Data Governance

### 5.1 Verification Scope Across Full Lifecycle

We traced credentials across 8 lifecycle stages:
1. **Inbound Telemetry:** Raw logs and trace spans.
2. **Validation Errors & Exceptions:** Masked in `SafeTelemetryHttpClient` and API responses.
3. **Application Logs & Audit Logs:** Masked via `mask_secret` and `redact_sensitive_text`.
4. **Database Persistence:** Integration credentials stored as masked previews (e.g. `Bearer ***e1a2`).
5. **Redis Cache:** Keys prefixed with `org_id` and contain no plaintext credentials.
6. **Celery Worker Payloads:** Task arguments contain sanitized request payloads.
7. **Investigation Prompts & LLM Egress:** All untrusted evidence sanitized prior to prompt assembly.
8. **Frontend Error Display:** Browser-visible payloads contain redacted strings (`[REDACTED_TOKEN]`).

### 5.2 Enhanced Redaction Scope

`redact_sensitive_text` was expanded to sanitize:
- **Bearer Tokens:** `Bearer [A-Za-z0-9-_\.]+` $\to$ `Bearer [REDACTED_TOKEN]`.
- **JSON Web Tokens (JWT):** `ey[A-Za-z0-9-_=]{10,}\.[A-Za-z0-9-_=]{10,}\.?[A-Za-z0-9-_.+/=]*` $\to$ `[REDACTED_JWT]`.
- **Database Connection URIs:** `postgresql://admin:secret123@db:5432/orders` $\to$ `postgresql://admin:[REDACTED_CREDS]@db:5432/orders`.
- **API Keys & Secrets:** `api_key=sk-ant-live...` $\to$ `api_key=[REDACTED]`.
- **Email Addresses & PII:** `alice@company.internal` $\to$ `[REDACTED_EMAIL]`.

Verified via `test_comprehensive_secret_redaction` and `test_prompt_sanitization_removes_secrets_and_injection`.

---

## 6. Read-Only Invariants & Mutating Protection Proof

### 6.1 Server-Side Enforcement

We verified that read-only protections are strictly enforced server-side and cannot be bypassed by client-side flag tampering:
- In `backend/app/agent/git/base.py`, `GitProvider` defaults to `read_only=True`.
- In `backend/app/agent/git/github_provider.py`:
  - `create_branch` checks `if self.read_only: raise PermissionError(...)`.
  - `create_pull_request` checks `if self.read_only: raise PermissionError(...)`.
  - Protected branches (`main`, `master`, `production`, `prod`, `release`, `stable`) are rejected by server-side guards.
- In `backend/app/agent/git/local_provider.py`:
  - `create_branch` and `create_pull_request` check `if self.read_only: raise PermissionError(...)`.
- In `backend/app/agent/services/repair_service.py`:
  - `approve_or_reject_repair` records human approval status in the database, but does **not** push to Git, create remote PRs, or deploy code to production.

Verified via `test_read_only_git_operations_strictly_fail_closed` and `test_repair_workflow_produces_read_only_pilot_report`.

---

## 7. Kill-Switches, Emergency Aborts & Celery Background Execution

### 7.1 Kill-Switch Controls Audited

1. **`investigations_paused`:**
   - Verified that `POST /agent/investigations` immediately returns `HTTP 403 FORBIDDEN` when paused.
   - Updated `investigate_incident_task` in `backend/workers/tasks.py` to inspect `PilotGovernancePolicy.investigations_paused`. In-flight and queued Celery tasks abort cleanly with `{"status": "aborted"}` without calling LangGraph.
2. **`collection_enabled`:**
   - In `backend/app/agent/graph/nodes/gather_evidence.py`, verified that when `collection_enabled=False`, telemetry evidence gathering is skipped and deterministic fallback is engaged.
3. **`allow_external_llm`:**
   - In `backend/app/agent/graph/nodes/evaluate_hypotheses.py`, verified that external model dispatch is blocked unless explicitly authorized.
4. **Integration Disconnect & Revocation:**
   - Disconnecting or revoking a repository immediately prevents any repair inspection or patch generation without requiring a server restart.

Verified via `test_investigations_paused_kill_switch_in_worker` and `test_investigations_paused_kill_switch`.

---

## 8. Independent Audit of Pilot Replay Evaluation & Benchmark Grounding

We audited the artifacts and results in `evaluation/results/shadow_pilot_cases.json`, `evaluation/results/shadow_pilot_verification_report.md`, and `evaluation/run_pilot_benchmark.py`:

### 8.1 Truthful Provenance & Sample Size Disclosure

- **Live Production Incidents:** **0** (honestly disclosed; customer VPC telemetry is NOT deployed).
- **Sanitized Postmortem Replays:** **10** (`PILOT-CASE-01` through `PILOT-CASE-10`).
- **Telemetry Provenance Label:** Clearly designated as `SANITIZED_REPLAY_FIXTURE` in all JSON records and UI views.
- **Live Telemetry Verified:** Explicitly marked as `false` across all records.

### 8.2 Accuracy & Abstention Metrics Reproduction

We independently verified the scoring math across the 10 sanitized replay cases:
- **Top-1 Accuracy:** $8 / 10 = 80.0\%$
- **Top-3 Recall:** $8 / 10 = 80.0\%$
- **Mean Reciprocal Rank (MRR):** $0.80$
- **Citation Validity:** $100\%$ (All claims cite verified evidence IDs; zero hallucinations).
- **Intentional Abstentions:** $2 / 2 = 100\%$ (Cases 7 and 10 correctly abstained on planned maintenance and transient network noise).
- **Operator Confirmed Rate:** $80.0\%$ ($8$ confirmed, $2$ rejected).
- **Operator Utility:** $90.0\%$ ($9 / 10$ cases materially assisted on-call SRE triage).

### 8.3 Answer Key Isolation Audit

We inspected `evaluation/benchmarks/held_out_incidents/ground_truth/answer_keys.json`:
- Answer keys are loaded in a separate directory and accessed strictly during post-investigation evaluation scoring.
- Prompt builders, LangGraph nodes, and vector stores have no references to answer keys or ground-truth files.
- `git grep -i "INC-PILOT" backend/app/` yielded zero hardcoded test case references.

---

## 9. Final Audit Verdict & Operational Pilot Gate Decision

### Verdict: **CONDITIONAL GO**

### Authorized Pilot Scope & Operating Boundaries:
1. **Mode:** **Sanitized Postmortem Replay Mode & Supervised Read-Only Shadow Mode ONLY.**
2. **Telemetry Ingress:** Strictly via sanitized replay files or authorized internal endpoints (`localhost` or explicit VPC internal collectors).
3. **Zero Automated Mutations:** Vermithor must **NOT** be granted write permissions to production Git repositories, CI/CD pipelines, Kubernetes clusters, or cloud management consoles.
4. **Data Handling & LLM Egress:** Customer telemetry must remain within the authorized organization perimeter (`allow_external_llm=False` by default). External LLM queries require explicit organizational policy opt-in.
5. **Emergency Readiness:** Operators must verify the accessibility of the administrative kill-switches (`investigations_paused` and `collection_enabled`) prior to commencing pilot sessions.

With all critical and high findings remediated and verified with 79 passing automated tests, Vermithor meets all security, safety, and reliability prerequisites for a supervised, read-only customer pilot.
