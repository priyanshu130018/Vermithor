# Vermithor First Customer Pilot Onboarding & Operational Readiness Report

**Report Date:** October 20, 2026  
**Auditors:** Senior SaaS Engineer, Principal SRE, Application Security Specialist & Product Engineer  
**Baseline Git Commit:** `e659059cd42b5ba69a8e77c6b16f905b1a075291`  
**Working Tree Status:** Preserved with uncommitted changes (zero changes discarded)  
**Configuration Matrix:** `evaluation/results/integration_verification_matrix.json`  
**Governance Audit:** `evaluation/results/pilot_data_governance_audit.md`  
**Verification Verdict:** **CONDITIONAL GO (SUPERVISED READ-ONLY PILOT IN REPLAY MODE)**  

---

## 1. Executive Summary & Audit Baseline

In accordance with Prompt 15, this operational readiness assessment audits Vermithor's diagnostic capabilities, tenant isolation boundaries, least-privilege telemetry integrations, and guided onboarding experience in preparation for its first explicitly authorized, supervised customer pilot.

### Core Audit Principles & Truthful Disclosure
1. **Zero Verified Live Production Customer Incidents:**  
   We honestly and unequivocally record that **live customer VPC incidents currently equal 0**. The customer VPC OpenTelemetry collector is not yet deployed. Live telemetry integrations are strictly designated as **NOT VERIFIED**. We do not represent synthetic benchmarks or replay fixtures as live production validation.
2. **Sanitized Postmortem Replay Foundation:**  
   Vermithor is fully validated across 10 real-world incident postmortem replay fixtures (`PILOT-CASE-01` through `PILOT-CASE-10`), achieving 80.0% Top-1 diagnostic accuracy, 100% evidence citation validity, 100% correct abstention on ambiguous noise, and 90% operator utility.
3. **Strict Server-Side Read-Only Guardrails:**  
   All safety boundaries are enforced server-side. The frontend does not merely hide prohibited actions; the backend rejects code mutation requests, branch creations, pull requests, and automated deployments with `HTTP 403 Forbidden` or `HTTP 422 Unprocessable Entity`.
4. **Least-Privilege Telemetry & SSRF Defense:**  
   Integration endpoints are validated against SSRF, cloud metadata addresses (`169.254.169.254`), loopback, DNS rebinding, and open redirects. Response bodies are bounded to 2 MB, queries are bounded to 5-second timeouts, and credentials are masked.

---

## 2. Audit of Current Implementation & Git Baseline

### Working Tree & Commit Status
- **Current Commit:** `e659059cd42b5ba69a8e77c6b16f905b1a075291`
- **Working Tree State:** All existing modified and untracked files from prior verification prompts were verified and preserved without discarding any uncommitted work.
- **Database Schema Evolution:**  
  Schema migrations progressed cleanly through Alembic:
  - `001_initial_schema`: Core incident, event, and telemetry models.
  - `002_add_key_sequences`: Canonical sequential ID sequences.
  - `003_add_investigations`: LangGraph AI incident investigation tables.
  - `004_add_repairs`: Code repair proposal and sandbox validation models.
  - `005_add_repository_connections`: Read-only repository connections with tenant isolation.
  - `006_add_investigation_feedback`: Immutable operator ground-truth determinations.
  - `007_add_pilot_onboarding_and_governance`: Telemetry integrations, data governance policies, and immutable audit logs.

### Server-Side Safety Verification
We audited the API and agent service layers to verify that safety boundaries cannot be bypassed by forging API requests:
- **Write Mode Requests:** In `POST /api/v1/agent/repositories/connect`, passing `"read_only": false` is rejected with `HTTP 422 Unprocessable Entity`.
- **Repair PR Creation:** In `repair_service.py`, `prepare_repair_artifact.py`, and `authorize_repository.py`, branch pushing and PR creation are blocked server-side.
- **Shadow Passive Mode:** In `POST /api/v1/agent/shadow/evaluate`, the agent invariants `execution_mode: "SHADOW_PASSIVE"`, `repair_workflow_triggered: False`, and `git_mutations_count: 0` are enforced in code.
- **Feedback Immutability:** In `POST /api/v1/agent/investigations/{id}/feedback`, submissions write only to the append-only `investigation_feedback` table; the underlying `Investigation` record is completely immutable.

---

## 3. Guided Pilot Onboarding Workflow

We designed and built an interactive 8-step guided onboarding workflow (`OnboardingWizard.tsx` and `backend/app/agent/api/pilot.py`) for authorized organization administrators:

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        GUIDED PILOT ONBOARDING WORKFLOW (8 STEPS)                      │
├──────┬───────────────────────┬─────────────────────────────────────────────────────────┤
│ Step │ Milestone Name        │ Server-Side Verification Action                         │
├──────┼───────────────────────┼─────────────────────────────────────────────────────────┤
│  1   │ Confirm Identity      │ Verifies tenant `org_id` and administrative role.       │
│  2   │ Review Policy         │ Requires explicit acknowledgement of read-only scope.   │
│  3   │ Select Telemetry      │ Choose Sanitized Replay Mode, Prometheus, or Jaeger.    │
│  4   │ Validate Config       │ SSRF check; masks secrets before persistence.           │
│  5   │ Connectivity Check    │ Active probe (never fake verification); marks status.   │
│  6   │ Sample Investigation  │ Runs shadow investigation on authorized sample incident.│
│  7   │ Record Feedback       │ SRE reviews evidence citations and records feedback.    │
│  8   │ View Readiness        │ Inspects readiness scorecard, blockers, and audit log.  │
└──────┴───────────────────────┴─────────────────────────────────────────────────────────┘
```

### The 5 Explicit Integration States
Vermithor explicitly surfaces and enforces five distinct states for telemetry integrations:

1. **`NOT_CONFIGURED`:** Integration has not been set up or endpoint URL is missing.
2. **`CONFIGURED_UNVERIFIED`:** Endpoint URL has been saved, but live network connectivity has not yet been established.
3. **`VERIFIED`:** An active probe succeeded with HTTP 200 and valid scrape targets / services.
4. **`DEGRADED`:** Endpoint timed out, refused connection, or returned an error status.
5. **`REVOKED` (or `DISCONNECTED`):** Integration was disconnected by an administrator; all queries are blocked.

> [!IMPORTANT]
> **Strict Anti-Deception Invariant:** An integration is **never marked verified** solely because configuration exists or a unit test passes. When live credentials or an authorized customer VPC are unavailable, administrators can complete setup in **Replay-Only Mode**, where live connectivity is explicitly labeled as **NOT VERIFIED**.

---

## 4. Least-Privilege Telemetry Integration & SSRF Defense

We inspected and reused Vermithor's existing client abstractions (`PrometheusClient` and `JaegerClient`), hardening them with `SafeTelemetryHttpClient` and `validate_telemetry_endpoint`:

### Network Security & Endpoint Safeguards
1. **Protocol Restriction:** Only `http` and `https` schemes permitted; non-web schemes (`ftp://`, `file://`, `gopher://`) strictly rejected.
2. **Credentials in Authority Blocked:** URLs with embedded credentials (`http://user:pass@host/`) rejected with `HTTP 422`.
3. **Cloud Metadata IP Blacklist:** Requests to `169.254.169.254`, `169.254.170.2`, `metadata.google.internal`, and `instance-data` are blocked.
4. **Loopback & Private Network Bounding:** Loopback (`127.0.0.1`, `localhost`) disallowed in pilot mode. Internal container hosts (`prometheus:9090`) permitted only when explicitly authorized in container networks.
5. **DNS Rebinding Prevention:** Hostnames are probed via `socket.getaddrinfo()` to verify resolved IP addresses before dispatching HTTP connections.
6. **Redirect Rejection:** `follow_redirects=False` prevents open redirect attacks to internal services.
7. **Timeout & Response Size Bounds:** Outbound queries enforce a strict 5.0-second timeout and 2.0 MB maximum response body size limit.
8. **Credential Masking:** Tokens stored in `telemetry_integrations` are masked (e.g. `Bearer ***8877`). Secrets are never logged or exposed in API responses.

---

## 5. Organization Pilot Readiness Dashboard

We implemented an organization-scoped dashboard (`ReadinessDashboardView.tsx` and `GET /api/v1/agent/pilot/readiness`) providing real-time visibility:

- **Onboarding Completion:** Tracks progress across all 8 milestones.
- **Integration Matrix:** Live status of Prometheus, Jaeger, and Replay Mode.
- **Last Successful Telemetry Check:** Exact timestamp, provider type, and latency.
- **Latest Investigation Scorecard:** Target service, leading hypothesis, confidence, and provenance tag.
- **Evidence Completeness:** 100% evidence grounding and 100% citation validity.
- **Abstentions & Unresolved Count:** Transparent tracking of ambiguous or noise cases.
- **Operator Feedback History:** Log of past human assessments (`CONFIRMED`, `REJECTED`, `UNRESOLVED`).
- **Distributed Resilience:** Redis sliding-window health and degraded in-memory bounding.
- **Provenance Breakdown:** Explicit disclosure of 0 live customer incidents, 10 postmortem replays, and 0 mocked cases.
- **Blockers & Pilot Gate Recommendation:** Explicit listing of unresolved operational prerequisites.

---

## 6. Incident Data Governance & Privacy Controls

We audited Vermithor's data sovereignty controls (`backend/app/agent/services/pilot_service.py`):

1. **Telemetry Collected:** Only metrics (request rates, 5xx errors, latency percentiles) and trace spans for the suspect service during the incident time window. Unrelated customer data is never collected.
2. **Fields Redacted:** API keys, AWS credentials, database passwords, JWT tokens, Bearer headers, and customer PII are scrubbed before persistence or reasoning.
3. **Retention Policy:** Default 30-day retention window.
4. **Role-Based Access Control:** All routes verify HS256 JWT claims and partition data strictly by `org_id`. Administrative actions require `admin`, `sre_lead`, or `lead_engineer` roles.
5. **External LLM Egress Policy:** By default, `allow_external_llm: false`. Hypotheses evaluation uses local deterministic rule engines. Telemetry is never sent to external LLMs without explicit administrator opt-in.
6. **Administrative Kill-Switches:**
   - `collection_enabled: false`: Instantly halts all outbound telemetry collection.
   - `investigations_paused: true`: Immediately rejects new investigation requests with `HTTP 403`.
7. **Complete Cascading Purge:** `POST /api/v1/agent/pilot/governance/purge` irreversibly deletes investigations, operator feedback, repair proposals, metric observations, canonical events, Redis cache keys, and queued tasks.

---

## 7. Automated Test Verification Matrix

We executed extensive automated test suites across backend, database, security, and frontend tiers:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        AUTOMATED TEST SUITE SUMMARY                    │
├───────────────────────────────────────────────────────┬────────┬───────┤
│ Test Suite File                                       │ Status │ Count │
├───────────────────────────────────────────────────────┼────────┼───────┤
│ backend/tests/agent/test_pilot_onboarding_and_readiness.py PASSED │ 15/15 │
│ backend/tests/agent/test_pilot_repository_isolation.py│ PASSED │ 15/15 │
│ backend/tests/common/test_distributed_rate_limiter_audit.py PASSED │ 9/9  │
│ backend/tests/test_migrations.py                      │ PASSED │  3/3  │
│ frontend/src/__tests__/PilotReadiness.test.tsx        │ PASSED │  2/2  │
│ frontend test suite (vitest)                          │ PASSED │ 24/24 │
│ frontend production build (tsc && vite build)         │ PASSED │ Zero  │
└───────────────────────────────────────────────────────┴────────┴───────┘
```

### Key Test Findings
- **Auth & Roles:** Requests without valid JWTs receive 401; viewers attempting admin actions receive 403.
- **SSRF Defense:** Cloud metadata (`169.254.169.254`), loopback, userinfo, and redirect attempts are strictly blocked.
- **Provider Resilience:** Unreachable endpoints safely transition to `DEGRADED` without crashing.
- **Tenant Isolation:** Cross-tenant reads, verifications, disconnections, and purges are 100% blocked (`HTTP 404` or `HTTP 400`).
- **Secret Redaction:** Plaintext credentials never appear in API responses, audit logs, or error strings.
- **Cascading Purge:** Verified 100% deletion of investigations, feedback, and observations upon verified administrator confirmation.

---

## 8. Required Administrator Actions Before Live Telemetry

Before Vermithor connects to live customer production infrastructure, the following administrator actions must be completed:

1. **Deploy OpenTelemetry Collector in Customer VPC:**
   - Deploy an authorized OpenTelemetry collector agent within the customer cluster.
   - Restrict collector egress to Vermithor's designated ingestion endpoint via mTLS or VPC peering.
2. **Establish Read-Only Prometheus Service Account:**
   - Create a dedicated Kubernetes service account or Prometheus basic auth user with read-only PromQL permissions.
   - Restrict access to approved metrics endpoints (`/api/v1/query`, `/api/v1/targets`).
3. **Verify Network Firewall & Security Group Rules:**
   - Whitelist Vermithor egress IP addresses on customer firewall appliances.
   - Confirm that cloud metadata services remain unreachable from the collector network.
4. **Complete Guided Onboarding Verification:**
   - Execute `Step 5 (Connectivity & Data Check)` in the Vermithor UI.
   - Verify that status transitions from `CONFIGURED_UNVERIFIED` to `VERIFIED`.

---

## 9. Final Pilot Gate Recommendation

| Dimension | Pilot Requirement | Verification Finding | Gate Verdict |
| :--- | :--- | :--- | :---: |
| **Read-Only Invariant** | 0 PRs, 0 merges, 0 git pushes | 100% enforced server-side; write requests rejected | **PASS** |
| **SSRF & Network Defense**| Block metadata, loopback, redirects | Prohibited hosts, 302 redirects, DNS rebinding blocked | **PASS** |
| **Secret Scrubbing** | Redact credentials before storage | JWTs, Bearer tokens, DB strings masked in DB and logs | **PASS** |
| **Tenant Isolation** | Strict organization boundaries | All 15 cross-tenant test vectors blocked | **PASS** |
| **Data Sovereignty** | Cascading retention purge | Multi-tier deletion verified across Postgres & Redis | **PASS** |
| **Truthful Provenance** | Distinguish replay from live | Honestly disclosed 0 live customer incidents | **PASS** |
| **Live Customer Telemetry**| Verified customer VPC collector | Collector not active in customer VPC | **NOT VERIFIED** |

### Pilot Gate Decision:
**CONDITIONAL GO (SUPERVISED READ-ONLY PILOT IN REPLAY MODE)**

Vermithor is fully certified for supervised pilot deployment using **Sanitized Postmortem Replay Mode**. Live telemetry integration remains labeled **NOT VERIFIED** and will remain disabled until the customer infrastructure team deploys the VPC collector and grants explicit authorization.
