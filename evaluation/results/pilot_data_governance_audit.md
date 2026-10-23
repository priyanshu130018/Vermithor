# Vermithor Pilot Incident Data Governance & Privacy Audit Report

**Audit Date:** October 20, 2026  
**Auditor:** Senior SRE, Application Security Engineer & Data Privacy Specialist  
**Target Repository Commit:** `e659059cd42b5ba69a8e77c6b16f905b1a075291`  
**Configuration Matrix:** `evaluation/results/integration_verification_matrix.json`  
**Readiness Report:** `evaluation/results/first_customer_pilot_readiness.md`  

---

## 1. Executive Summary & Governance Objectives

This audit establishes and verifies the incident data governance framework for Vermithor's first supervised customer pilot.

In enterprise and regulated cloud environments, AI diagnostic tools must guarantee that customer telemetry is handled with least-privilege access, strict tenant boundary isolation, automatic credential scrubbing, and verifiable data deletion.

### Core Governance Invariants
1. **Zero Customer Infrastructure Modification:** Vermithor never modifies clusters, deployments, network ingress, or cloud configurations.
2. **Zero Automated Code Mutations:** Vermithor never pushes branches, creates pull requests, merges code, or triggers deployment pipelines during the pilot phase.
3. **No Unrestricted URL Fetching / SSRF Defense:** All outbound requests are validated against private network addresses, loopback endpoints, cloud metadata services (`169.254.169.254`), and open redirects.
4. **Pre-Persistence Secret Scrubbing:** Sensitive tokens, database credentials, AWS keys, and JWTs are stripped before storage, logging, embedding, or reasoning.
5. **Zero External LLM Egress without Authorization:** Telemetry stays local and is evaluated via deterministic rules unless the organization administrator explicitly opts in.
6. **Verifiable Multi-Tier Data Deletion:** Purge operations cascade across database records, related evidence, Redis cache keys, and queued Celery worker tasks.

---

## 2. Telemetry Ingestion Scope & Least Privilege

Vermithor operates under a strict pull-based telemetry model. It never sweeps or collects arbitrary or unrelated customer telemetry.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        DATA INGESTION BOUNDARIES                       │
├───────────────────┬────────────────────────────────┬───────────────────┤
│ Data Category     │ Specific Fields Collected      │ Access Level      │
├───────────────────┼────────────────────────────────┼───────────────────┤
│ Service Metrics   │ • http_requests_total          │ Read-Only PromQL  │
│                   │ • http_request_duration_bucket │ (Instant & Range) │
│                   │ • active_requests              │                   │
│                   │ • Scoped only to failing svc   │                   │
├───────────────────┼────────────────────────────────┼───────────────────┤
│ Distributed Traces│ • Root operation name & latency│ Read-Only Jaeger  │
│                   │ • Error flag & error spans     │ Query API         │
│                   │ • Service dependency topology  │                   │
├───────────────────┼────────────────────────────────┼───────────────────┤
│ Incident Context  │ • Target service name          │ Incident Service  │
│                   │ • Incident timestamp & lookback│ Database / API    │
│                   │ • Anomaly observations         │                   │
├───────────────────┼────────────────────────────────┼───────────────────┤
│ Source Code       │ • Suspect source files only    │ Read-Only GitHub  │
│                   │ • Commit SHA & branch name     │ App / PAT         │
│                   │ • Repository metadata          │                   │
├───────────────────┼────────────────────────────────┼───────────────────┤
│ Prohibited Data   │ • Customer database payloads   │ STRICTLY BLOCKED  │
│                   │ • User passwords / sessions    │                   │
│                   │ • Private keys / secrets       │                   │
│                   │ • Unrelated cluster metrics    │                   │
└───────────────────┴────────────────────────────────┴───────────────────┘
```

---

## 3. Secret Scrubbing & Data Redaction Engine

Before any gathered metric, log entry, trace span, or error message is persisted, indexed into vector embeddings, or processed by reasoning graphs, it passes through `redact_sensitive_text()` and `redact_sensitive_strings()`.

### Scrubbed Secret Categories

| Secret Category | Detection Pattern | Scrubbed Replacement |
| :--- | :--- | :--- |
| **OpenAI / Anthropic Keys** | `(?i)sk-(?:ant-)?[a-zA-Z0-9_\-]{20,}` | `[REDACTED_SECRET]` |
| **AWS Access / Secret Keys**| `AKIA[0-9A-Z]{16}` | `[REDACTED_SECRET]` |
| **Database Connection Strings**| `(?:postgres\|mysql\|redis)://[^:\s]+:[^@\s]+@[^\s]+` | `postgres://user:[REDACTED]@host/db` |
| **Bearer Tokens & Passwords**| `(?i)bearer\s+[A-Za-z0-9\-_.]+` | `Bearer [REDACTED_TOKEN]` |
| **JSON Web Tokens (JWT)** | `ey[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?...` | `[REDACTED_JWT]` |
| **Masked Stored Credentials**| Integration configuration tokens | `Bearer ***8877` (first 6 chars masked) |

---

## 4. Multi-Tenant Access Control & Visibility

All Vermithor API endpoints enforce cryptographically signed HS256 JWT tokens. Data is partitioned by `org_id`:

1. **Organization Boundary Enforcement:**
   - Every database query for investigations, feedback, repository connections, telemetry integrations, and audit logs filters strictly on `org_id == tenant_org`.
   - Cross-tenant access is tested and verified: Organization B receives `HTTP 404 Not Found` or `HTTP 403 Forbidden` when attempting to query or mutate Organization A's resources.
2. **Role-Based Administrative Guardrails:**
   - Operational actions (configuring integrations, verifying endpoints, updating data retention policies, pausing collection, or purging data) require an administrative role (`admin`, `sre_lead`, `lead_engineer`, `org_admin`).
   - Read-only viewers (`role: "viewer"`) attempting administrative actions are rejected with `HTTP 403 Forbidden`.
3. **Investigation Immutability:**
   - Operator feedback records determinations in the `investigation_feedback` table.
   - Feedback never mutates or overwrites historical `investigations` records (`leading_hypothesis`, `confidence`, `report_json`).
   - Operator feedback is never fed into automated training pipelines without explicit customer authorization.

---

## 5. External LLM Data Transmission Policy

A primary concern during customer pilots is whether customer telemetry is transmitted to third-party model providers (e.g. OpenAI, Anthropic, or external cloud endpoints).

### Pilot Policy Rules
- **Default Invariant:** `allow_external_llm: false`.
- When `allow_external_llm == false`:
  - Hypotheses evaluation executes strictly using Vermithor's **deterministic rule engine** (`_build_deterministic_evaluation`).
  - No prompt containing customer metric names, error traces, or service topology is dispatched across the network to any third-party API.
- **Explicit Administrator Opt-In:**
  - An organization administrator can authorize external LLM egress only by submitting `POST /api/v1/agent/pilot/governance/policy` with `{"allow_external_llm": true}`.
  - Every policy update is recorded in the immutable `pilot_audit_logs` table.

---

## 6. Integration Revocation & Disconnection Behavior

When an organization administrator disconnects a telemetry integration via `POST /api/v1/agent/pilot/integrations/{id}/disconnect`:
1. The integration status is immediately marked as `REVOKED`.
2. `is_verified` is set to `False` and `telemetry_provenance` is set to `NOT_VERIFIED`.
3. All cached credentials and tokens are wiped.
4. Subsequent polling, verification checks, or background investigation tasks targeting this integration immediately halt with `HTTP 404` or `PermissionError`.
5. An audit event `INTEGRATION_DISCONNECTED` is logged with the actor's identity and timestamp.

---

## 7. Organization Data Deletion & Cascading Retention Purge

Under the Vermithor Data Governance Framework, organizations maintain full data sovereignty. Collected incident data is retained for a configurable window (default: 30 days) and can be immediately purged upon administrator request.

### Cascading Purge Scope (`POST /api/v1/agent/pilot/governance/purge`)

```
                                PURGE REQUEST
                      (confirm_organization_id: "org_alpha")
                                      │
               ┌──────────────────────┴──────────────────────┐
               ▼                                             ▼
     [ PostgreSQL Database ]                         [ Distributed Cache ]
     • investigations                                • Redis cache keys
     • investigation_feedback                        • Cached PromQL responses
     • repairs & validation patches                  • Session state tokens
     • metric_observations                           
     • canonical events & traces                     [ Background Queues ]
                                                     • Revoke queued Celery tasks
```

### Complete Purge Verification
- The purge API requires explicit confirmation of `confirm_organization_id`. Mismatches are rejected with `HTTP 400 Bad Request`.
- Verification tests in `test_organization_data_purge` confirm that:
  - 100% of persisted investigation records are deleted.
  - 100% of operator feedback records are deleted.
  - 100% of telemetry observations and trace events are deleted.
  - Redis cache keys matching the tenant pattern are purged.
  - The deletion is recorded in `pilot_audit_logs` with exact counts of deleted records.

---

## 8. Administrative Kill-Switches

To give customer SREs instant operational control during an incident or maintenance window, Vermithor implements two distinct kill-switches:

1. **Telemetry Collection Kill-Switch (`collection_enabled: false`):**
   - Instantly halts all outgoing requests to customer Prometheus, Jaeger, or OTel endpoints.
   - Ongoing investigations gracefully fall back to local cached observations and sanitized replay records.
2. **Investigation Pause Kill-Switch (`investigations_paused: true`):**
   - Rejects all incoming investigation triggers (`POST /api/v1/agent/investigations`) with `HTTP 403 Forbidden`.
   - Protects customer infrastructure during cluster maintenance or network degradation.

---

## 9. Immutable Audit Trail

All administrative, configuration, verification, disconnection, and deletion operations are recorded in `pilot_audit_logs`:

| Action | Resource Type | Recorded Fields |
| :--- | :--- | :--- |
| `ONBOARDING_STEP_COMPLETED` | `ONBOARDING` | Step identifier, notes, read-only acknowledgement |
| `INTEGRATION_CONFIGURED` | `INTEGRATION` | Provider type, name, sanitized endpoint URL |
| `INTEGRATION_VERIFIED` | `INTEGRATION` | Provenance label, probe latency, active target count |
| `INTEGRATION_DISCONNECTED`| `INTEGRATION` | Provider name, revocation timestamp |
| `DATA_POLICY_UPDATED` | `POLICY` | Modified governance fields (kill-switches, LLM egress) |
| `DATA_PURGED` | `DATA_PURGE` | Counts of deleted investigations, feedback, and observations |

Logs cannot be modified or deleted via the API and provide a verifiable audit trail for compliance and security review.
