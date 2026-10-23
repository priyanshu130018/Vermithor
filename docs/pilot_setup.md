# Vermithor Controlled Pilot & Read-Only Repository Setup Guide

This guide details the procedure for safely onboarding a dedicated test repository into Vermithor during the **Controlled Pilot Phase**.

In pilot mode, Vermithor operates with **strictly read-only permissions**. The agent inspects authorized source files, proposes minimal evidence-grounded patches, and validates them inside isolated temporary sandboxes. It **strictly does not** create remote branches, open pull requests, push commits, merge code, or deploy changes to any live environment.

---

## 1. Security Architecture & Least Privilege

```
+-------------------------------------------------------------+
|                     Vermithor Platform                      |
|                                                             |
|  +--------------------+        +-------------------------+  |
|  | LangGraph Agent    |        | Isolated Sandbox Runner |  |
|  | (Investigation &   |        | (HOST_SUBPROCESS_       |  |
|  |  Repair Reasoning) |        |  RESTRICTED)            |  |
|  +---------+----------+        +------------+------------+  |
|            |                                |               |
|            v                                v               |
|  +-------------------------------------------------------+  |
|  | Read-Only Git Provider Interface                      |  |
|  | (contents: read, metadata: read)                      |  |
|  +---------------------------+---------------------------+  |
+------------------------------|------------------------------+
                               | HTTPS (Read-Only)
                               v
               +-------------------------------+
               | GitHub Remote / Local Mirror  |
               | (Dedicated Test Repository)   |
               +-------------------------------+
```

### Permission Model
Vermithor requests only the minimum read-only permissions:

| Permission | Access Level | Purpose |
| :--- | :--- | :--- |
| **Repository Contents** | `Read-only` | Inspect source files identified in investigation hypotheses. |
| **Repository Metadata** | `Read-only` | Query repository existence, default branch, and commit SHAs. |
| **Pull Requests** | `No access` (or `None`) | Write operations disabled during pilot phase. |
| **Administration / Secrets** | `No access` | Prohibited across all environments. |

---

## 2. GitHub App Configuration

To connect a repository via GitHub App:

1. **Create GitHub App**:
   - Navigate to **GitHub Settings → Developer Settings → GitHub Apps → New GitHub App**.
   - Set **GitHub App name**: `Vermithor-Incident-Repair-Pilot`.
   - Set **Homepage URL**: `https://vermithor.internal`.
   - Disable **Webhook** (active=false) or set to internal webhook handler.

2. **Configure Repository Permissions**:
   - `Contents`: **Read-only**
   - `Metadata`: **Read-only**
   - All other permissions: **No access**

3. **Generate Private Key & Installation ID**:
   - Generate a private key (`.pem`) and download it securely.
   - Install the GitHub App onto your **dedicated test repository only** (e.g., `vermithor-org/payment-service-pilot`).
   - Note the **Installation ID** from the installation settings URL (e.g. `https://github.com/settings/installations/12345678`).

---

## 3. Environment Variables Configuration

Configure the backend environment in your `.env` or container environment:

```bash
# ============================================================================
# Vermithor Pilot Mode Configuration
# ============================================================================
VERMITHOR_PILOT_MODE=true

# GitHub App Authentication (Recommended)
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY_PATH=/secrets/github-app-private-key.pem
GITHUB_APP_INSTALLATION_ID=12345678

# Alternative Token Authentication (Read-Only Fine-Grained PAT)
# Ensure token has only 'Contents: Read' and 'Metadata: Read' on the test repository
GITHUB_TOKEN=github_pat_xxxx_readonly

# Base GitHub API URL (defaults to https://api.github.com)
GITHUB_API_BASE_URL=https://api.github.com
```

> **Security Note:** Never commit `.pem` files or tokens to source control. Vermithor automatically redacts tokens from all logs, audit trails, and API responses.

---

## 4. Connecting a Repository

### Via REST API

Connect the repository using the authenticated API:

```http
POST /api/v1/agent/repositories/connect
Authorization: Bearer <JWT_TOKEN>
Content-Type: application/json

{
  "repo_identifier": "vermithor-org/payment-service-pilot",
  "installation_id": "12345678",
  "read_only": true
}
```

**Response (HTTP 201):**
```json
{
  "id": "c8f9b1d2-3e4a-4b5c-8d9e-1f2a3b4c5d6e",
  "org_id": "vermithor",
  "repo_identifier": "vermithor-org/payment-service-pilot",
  "installation_id": "12345678",
  "read_only": true,
  "status": "CONNECTED",
  "connected_by": "eng_lead@vermithor.io",
  "connected_at": "2026-10-19T14:30:00Z",
  "latest_commit_sha": "b4a2e8c9d01234567890abcdef1234567890abcd",
  "permissions": {
    "contents": "read",
    "metadata": "read"
  },
  "audit_notice": "Connected in Read-Only Pilot Mode: write operations (branch creation, PR creation, push) are strictly prohibited."
}
```

### Identifier Format Requirements
- Accepted: `owner/repo` (e.g. `vermithor-org/payment-service`) or `https://github.com/owner/repo`.
- Strictly rejected:
  - Directory traversal (`../`, `..\\`).
  - Null bytes (`\x00`) and control characters.
  - SSRF loopback/private hosts (`127.0.0.1`, `localhost`, `169.254.169.254`, `10.*`, `192.168.*`).
  - Write mode requests (`"read_only": false` is rejected with HTTP 422).

---

## 5. Verifying & Managing Connections

### Probe Connection Health & Rate Limits
```http
GET /api/v1/agent/repositories/{connection_id_or_slug}/verify
Authorization: Bearer <JWT_TOKEN>
```

**Response:**
```json
{
  "repo_identifier": "vermithor-org/payment-service-pilot",
  "status": "CONNECTED",
  "reachable": true,
  "read_only": true,
  "rate_limit_remaining": 4992,
  "latest_commit_sha": "b4a2e8c9d01234567890abcdef1234567890abcd",
  "message": "Repository verified and healthy in strict read-only pilot mode."
}
```

### Disconnect / Revoke Connection
```http
POST /api/v1/agent/repositories/{connection_id_or_slug}/disconnect
Authorization: Bearer <JWT_TOKEN>
```

**Response:**
```json
{
  "id": "c8f9b1d2-3e4a-4b5c-8d9e-1f2a3b4c5d6e",
  "repo_identifier": "vermithor-org/payment-service-pilot",
  "status": "REVOKED",
  "revoked_at": "2026-10-19T14:35:00Z",
  "message": "Repository 'vermithor-org/payment-service-pilot' successfully disconnected. Further inspection requests are blocked."
}
```

Once disconnected:
- Subsequent repair or inspection requests targeting this repository are immediately blocked (`PermissionError`).
- No cached tokens or credentials remain active.

---

## 6. Pilot Guardrails & Human Approval Boundary

During the pilot:
1. **Advisory Artifacts Only**:
   Repair runs generate unified diffs and execute sandbox tests, but will **never** push to GitHub. `pull_request_url` and `repair_branch` remain `null`.
2. **Human Approval Action**:
   In the UI or API, approving a repair registers review authorization and logs the decision. Approving does **not** push, merge, or trigger automated deployments.
3. **Multi-Tenant Isolation**:
   Organizations are strictly partitioned. Organization A cannot inspect, view, or connect Organization B's repositories.

---

## 7. Troubleshooting

| Symptom | Cause | Resolution |
| :--- | :--- | :--- |
| `HTTP 403 Forbidden: rate limit exceeded` | GitHub API rate limit reached on token/IP. | Wait for reset window or configure dedicated GitHub App installation token. |
| `HTTP 422: Write mode is strictly disabled` | Client passed `"read_only": false`. | Omit `read_only` or set to `true`. Write mode is disallowed during the pilot. |
| `HTTP 404: Repository connection not found` | Attempting to access another organization's connection. | Verify JWT `org_id` matches the connecting organization. |
| `PermissionError: Repository has been revoked` | Repository was previously disconnected. | Reconnect the repository via `POST /api/v1/agent/repositories/connect`. |

---

## 8. Pilot Benchmark & Resilience Verification

Before deploying or onboarding pilot customers, operators can run the deterministic evaluation harness and resilience test suite.

### Running the 12-Scenario Pilot Benchmark
The benchmark evaluates 12 realistic incidents covering database saturation, bad deployments, cache failures, resource exhaustion, and deliberate uncertainty/abstention cases:

```bash
# Execute the full 12-scenario evaluation harness
python evaluation/run_pilot_benchmark.py
```

Outputs generated:
- Machine-readable JSON: `evaluation/results/pilot_benchmark_results.json`
- Comprehensive human-readable report: `evaluation/results/pilot_benchmark_report.md`

### Running the Controlled Failures & Resilience Suite
To verify system behavior under GitHub rate limits, network timeouts, database outages, LLM failures, and sandbox timeouts:

```bash
pytest backend/tests/agent/test_controlled_failures_and_resilience.py -v
```

### Reviewing SaaS Readiness Audit
For security posture, tenant isolation, secret redaction, and multi-tenant scaling considerations, inspect:
- `evaluation/results/saas_readiness_audit.md`
- `evaluation/results/first_customer_pilot_readiness.md`
- `evaluation/results/pilot_data_governance_audit.md`

---

## 9. Guided Pilot Onboarding Workflow

Authorized organization administrators onboard into Vermithor through an 8-milestone guided workflow accessible via the UI (`/pilot`) or REST API:

1. **Confirm Organization Identity:** Verify tenant `org_id` and confirm administrator permissions (`admin`, `sre_lead`, `lead_engineer`).
2. **Review Read-Only Pilot Scope:** Formally acknowledge the strict read-only boundary (0 code pushes, 0 PR creations, 0 infrastructure mutations, PII redaction, 30-day retention).
3. **Select Telemetry Integration Mode:**
   - **Sanitized Replay Mode (Recommended for Phase 1):** Zero external network access; uses 10 independently verified postmortem replay fixtures. Live telemetry labeled **NOT VERIFIED**.
   - **Prometheus Metrics:** Read-only PromQL queries.
   - **Jaeger / OpenTelemetry:** Read-only trace queries.
4. **Validate Configuration (SSRF-Protected):** Endpoints validated against cloud metadata (`169.254.169.254`), loopback, DNS rebinding, and open redirects. Secret tokens masked in storage (`Bearer ***8877`).
5. **Execute Connectivity Check:** Real network probe to endpoint `/api/v1/targets` or `/api/services`. Never fakes verification.
6. **Execute Sample Investigation:** Run shadow-mode investigation against sample incident (`INC-PILOT-201`).
7. **Record Operator Feedback:** Human SRE reviews evidence citations and records ground-truth assessment (`CONFIRMED`, `REJECTED`, `UNRESOLVED`). Original AI diagnosis remains immutable.
8. **View Pilot Readiness Scorecard:** Inspect live blockers and pilot gate recommendation.

---

## 10. Least-Privilege Telemetry Integrations

Vermithor explicitly surfaces five operational states for each telemetry provider:

| Integration State | Definition | Probe Behavior |
| :--- | :--- | :--- |
| `NOT_CONFIGURED` | Provider has not been configured. | No outbound traffic. |
| `CONFIGURED_UNVERIFIED` | Endpoint URL saved; probe not yet executed. | Labeled NOT VERIFIED. |
| `VERIFIED` | Active probe returned HTTP 200 and healthy targets. | Provenance labeled LIVE or REPLAY. |
| `DEGRADED` | Endpoint unreachable, timed out, or returned error. | Labeled DEGRADED; safe error captured. |
| `REVOKED` | Administrator disconnected integration. | Outbound queries blocked; credentials wiped. |

### Outbound Network & Security Constraints
- **Protocol:** HTTPS enforced for public endpoints; HTTP permitted only for approved internal container networks.
- **SSRF Blocklist:** Cloud metadata services (`169.254.169.254`, `169.254.170.2`, `metadata.google.internal`), loopback (`127.0.0.1`), and multicast.
- **Redirects:** `follow_redirects=False` strictly rejects 301/302 redirects.
- **Bounding:** 5.0-second query timeout and 2.0 MB maximum response body size limit.
- **Redaction:** Authorization headers, bearer tokens, and passwords scrubbed before logging.

---

## 11. Incident Data Governance & Privacy Controls

Organizations maintain full data sovereignty:
- **Telemetry Ingested:** Only metrics and trace spans for the suspect service within the incident window. Unrelated customer telemetry is never collected.
- **Fields Redacted:** OpenAI/Anthropic keys (`sk-...`), AWS keys (`AKIA...`), database credentials, bearer tokens, JWTs, and credit card patterns scrubbed before persistence.
- **External LLM Egress Policy:** `allow_external_llm: false` by default. Hypotheses evaluated locally via deterministic rule engines. Telemetry is never sent to external LLMs without explicit admin opt-in.
- **Administrative Kill-Switches:**
  - `POST /api/v1/agent/pilot/governance/policy` with `collection_enabled: false` halts all outbound telemetry collection immediately.
  - Setting `investigations_paused: true` rejects incoming investigations with `HTTP 403`.
- **Cascading Retention Purge:** `POST /api/v1/agent/pilot/governance/purge` with confirmed `confirm_organization_id` permanently purges investigations, feedback, repairs, observations, events, Redis cache keys, and queued tasks.




---

## 12. Operational Security Warnings & Independent Pre-Pilot Checklist

Prior to initiating any supervised customer pilot session, administrators and lead SREs must review the following security invariants verified in the independent security audit (`evaluation/results/independent_security_audit.md`):

### 12.1 Operational Security Warnings
> [!CAUTION]
> **Zero Live Incidents Validated:** Vermithor currently has zero verified live customer production incidents. All diagnostic benchmarks are grounded in 10 sanitized historical postmortem replay fixtures evaluated in supervised shadow mode. Do not represent replay results as live production validation.

> [!WARNING]
> **Server-Side Enforcement Invariant:** Read-only boundaries are enforced server-side. Even if a modified client or script requests code commits or pull request creation, the backend will fail closed with `PermissionError`. Never disable server-side read-only flags in pilot deployments.

> [!IMPORTANT]
> **SSRF & DNS Rebinding Defenses:** Outbound telemetry queries are protected by `SSRFProtectedSyncBackend` which verifies the physical socket peer address (`sock.getpeername()[0]`) upon TCP connection establishment. Prohibited destinations (cloud metadata `169.254.169.254`, loopback, link-local, private networks, IPv4-mapped IPv6 `::ffff:...`, integer IPs `2852039166`, octals, and HTTP redirects) are intercepted and aborted at the socket layer before transmitting HTTP requests.

### 12.2 Emergency Kill-Switch Procedures
If unexpected telemetry anomalies or operational incidents occur during a pilot session:

1. **Pause All Investigations Immediately:**
   ```bash
   curl -X POST https://vermithor.internal/api/v1/agent/pilot/governance/policy \
     -H "Authorization: Bearer $ADMIN_JWT" \
     -H "Content-Type: application/json" \
     -d '{"investigations_paused": true}'
   ```
   *Effect:* Immediately rejects all new incoming investigations with `HTTP 403 Forbidden` and causes active/reserved Celery worker tasks to abort cleanly without running LangGraph.

2. **Halt All Outbound Telemetry Collection:**
   ```bash
   curl -X POST https://vermithor.internal/api/v1/agent/pilot/governance/policy \
     -H "Authorization: Bearer $ADMIN_JWT" \
     -H "Content-Type: application/json" \
     -d '{"collection_enabled": false}'
   ```
   *Effect:* Halts all Prometheus, Jaeger, and OpenTelemetry query dispatches; falls back strictly to local offline rule evaluation.

3. **Execute Cascading Data Purge:**
   ```bash
   curl -X POST https://vermithor.internal/api/v1/agent/pilot/governance/purge \
     -H "Authorization: Bearer $ADMIN_JWT" \
     -H "Content-Type: application/json" \
     -d '{"confirm_organization_id": "your-org-id", "purge_all_pilot_data": true}'
   ```
   *Effect:* Permanently purges all organization investigations, repairs, operator feedback, scoped observations, Redis cache entries, and queued tasks with full audit log entry.
