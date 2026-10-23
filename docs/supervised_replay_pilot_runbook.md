# Vermithor Supervised Replay Pilot Operator Runbook

**Audience:** Authorized Organization Administrators, Lead SREs, Incident Commanders, and Platform Engineers  
**Operating Mode:** Supervised Read-Only Sanitized Postmortem Replay Mode  
**Document Version:** `1.0.0`  
**Security Classification:** Strictly Read-Only; Live Customer VPC Telemetry NOT Connected

---

## 1. Overview & Authorized Pilot Scope

This runbook guides authorized operators through conducting a supervised, read-only customer pilot of Vermithor using pre-sanitized incident postmortem replay fixtures.

### Strict Safety Boundaries
- **Replay Only:** Evaluates incident investigations exclusively against sanitized historical postmortem fixtures.
- **Zero Customer Telemetry:** Live customer VPC endpoints (Prometheus, OpenTelemetry, Jaeger) are **NOT VERIFIED** and must remain unconfigured or disconnected.
- **Zero Code Mutations:** Automated code repairs, repository branch creation, pull requests, and Git remote pushes are **STRICTLY PROHIBITED**.
- **Zero External Egress:** Customer data and telemetry are never transmitted to external LLM providers (`allow_external_llm=false`).
- **Data Governance:** Tenant data is strictly isolated by server-side `org_id` claims, and cascading data retention purge is guaranteed safe and idempotent.

---

## 2. Pre-Flight Verification & Operator Authentication

### Step 2.1: Verify Docker Stack & Service Liveness
Verify that the Vermithor services are active and healthy:
```bash
docker compose ps
curl -s http://localhost:8000/health | jq .
curl -s http://localhost:8000/ready | jq .
```
Expected output:
```json
{
  "service": "vermithor-monolith",
  "status": "healthy"
}
```

### Step 2.2: Mint Administrator Token
Acquire an authenticated JWT token containing organization and administrator claims:
```bash
# Mint administrator token for your organization
export TOKEN=$(python -c "
from backend.app.common.security import create_access_token
print(create_access_token({
    'sub': 'sre_admin_operator',
    'org_id': 'customer_pilot_org',
    'role': 'admin'
}))
")
echo "Authenticated Bearer Token: $TOKEN"
```

Verify that non-admin tokens cannot access administrative pilot endpoints:
```bash
curl -s -X GET http://localhost:8000/api/v1/agent/pilot/readiness \
  -H "Authorization: Bearer not-a-valid-token"
# Expected response: HTTP 401 Unauthorized
```

---

## 3. Guided Pilot Onboarding Workflow

The onboarding workflow guides organization administrators through identity verification, policy review, and telemetry configuration.

### Milestone 1: Confirm Identity & Permissions
Confirm that the organization identity matches server-side claims:
```bash
curl -X POST http://localhost:8000/api/v1/agent/pilot/onboarding/step \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "step": "CONFIRM_IDENTITY",
    "notes": "Verified customer_pilot_org identity and administrative role"
  }'
```

### Milestone 2: Review & Acknowledge Read-Only Policy
Formally review and accept the strict read-only boundary and data handling policy:
```bash
curl -X POST http://localhost:8000/api/v1/agent/pilot/onboarding/step \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "step": "REVIEW_POLICY",
    "acknowledged_read_only": true,
    "notes": "Formally accepted read-only pilot scope, secret scrubbing, and 30-day retention"
  }'
```

### Milestone 3: Select Telemetry Mode (Replay-Only)
Select replay mode using sanitized postmortem fixtures without requesting live API credentials:
```bash
curl -X POST http://localhost:8000/api/v1/agent/pilot/onboarding/step \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "step": "SELECT_TELEMETRY",
    "notes": "Selected Sanitized Postmortem Replay Mode; Live telemetry is NOT VERIFIED"
  }'
```

### Milestone 4: Validate Configuration
Validate that live telemetry collection is disabled and secret scrubbing is enabled:
```bash
curl -X POST http://localhost:8000/api/v1/agent/pilot/onboarding/step \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "step": "VALIDATE_CONFIG",
    "notes": "Validated replay mode configuration without exposing credentials"
  }'
```

---

## 4. Executing a Replay Incident Investigation

### Available Sanitized Replay Incidents
The repository provides 10 pre-sanitized historical postmortem replay cases:

| Case ID | Incident Key | Service | Diagnostic Focus |
|---|---|---|---|
| `PILOT-CASE-01` | `INC-PILOT-201` | `payment-core` | HikariCP database connection pool exhaustion |
| `PILOT-CASE-02` | `INC-PILOT-202` | `identity-auth` | Okta IdP signing certificate expiration |
| `PILOT-CASE-03` | `INC-PILOT-203` | `catalog-cache` | Redis maxmemory key eviction storm |
| `PILOT-CASE-04` | `INC-PILOT-204` | `checkout-api` | Downstream connection timeouts (CoreDNS packet drop) |
| `PILOT-CASE-05` | `INC-PILOT-205` | `doc-renderer` | Ext4 filesystem inode exhaustion on `/tmp` |
| `PILOT-CASE-06` | `INC-PILOT-206` | `ingest-worker` | Container memory leak & Linux cgroup OOM killer |
| `PILOT-CASE-07` | `INC-PILOT-207` | `inventory-sync` | Scheduled backup nominal telemetry (Abstention check) |
| `PILOT-CASE-08` | `INC-PILOT-208` | `fulfillment-stream` | Kafka consumer lag poison pill message |
| `PILOT-CASE-09` | `INC-PILOT-209` | `subscription-billing` | PostgreSQL row-level deadlocks during renewal billing |
| `PILOT-CASE-10` | `INC-PILOT-210` | `search-federator` | Transient cloud transit jitter (Abstention check) |

### Triggering an Investigation via API
Trigger an investigation for `INC-PILOT-201`:
```bash
curl -X POST http://localhost:8000/api/v1/agent/investigations \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "incident_key": "INC-PILOT-201",
    "lookback_minutes": 30,
    "force_refresh": true
  }' | jq .
```

### Retrieving and Inspecting Findings
Retrieve the generated investigation report:
```bash
curl -X GET http://localhost:8000/api/v1/agent/investigations/incident/INC-PILOT-201 \
  -H "Authorization: Bearer $TOKEN" | jq .
```

Inspect the diagnostic output:
- **`leading_hypothesis`**: Check primary root cause (e.g. `Database connection pool exhaustion on payment-core`).
- **`confidence`**: Verify score ($0.0$ to $1.0$). If confidence is below $0.45$, verify that status is `INSUFFICIENT_EVIDENCE`.
- **`evidence_items`**: Verify that all citations (`EV-METRIC-01`, `LOG-01`) reference valid telemetry signals and contain zero unredacted secrets or credentials.

---

## 5. Recording SRE Operator Verification Feedback

To validate AI triage accuracy without altering the underlying report or triggering model training, operators record their evaluation in the feedback interface.

### Recording Feedback via UI
1. Navigate to the incident in the Vermithor Web UI (`http://localhost:5173/incidents/INC-PILOT-201`).
2. Open the **Investigation Panel**.
3. Under **Operator Verification Assessment**, select:
   - **Confirm Diagnosis** (if the AI correctly identified the root cause)
   - **Reject Diagnosis** (if the AI misidentified the root cause)
   - **Mark Unresolved** (if telemetry was inconclusive or ambiguous)
4. Provide the confirmed root cause, cite supporting evidence, and enter notes explaining the triage impact.
5. Click **Submit Feedback**.

### Recording Feedback via API
```bash
curl -X POST http://localhost:8000/api/v1/agent/investigations/INV-REHEARSAL-201/feedback \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "investigation_key": "INV-REHEARSAL-201",
    "incident_key": "INC-PILOT-201",
    "feedback_status": "CONFIRMED",
    "confirmed_root_cause": "PostgreSQL connection acquisition timeout (HikariPool active=80/80)",
    "evidence_reference": "METRIC-hikari_active_connections_ratio=1.0",
    "explanation": "Vermithor correctly isolated pool exhaustion within 10s, directly guiding pool resizing."
  }' | jq .
```

### Verifying Feedback Immutability
Verify that recording feedback created a separate feedback entry and did **not** modify the original investigation report:
```bash
# Check original investigation (must remain 100% identical)
curl -s http://localhost:8000/api/v1/agent/investigations/INV-REHEARSAL-201 \
  -H "Authorization: Bearer $TOKEN" | jq '.leading_hypothesis, .confidence'

# Check recorded feedback entry
curl -s http://localhost:8000/api/v1/agent/investigations/INV-REHEARSAL-201/feedback \
  -H "Authorization: Bearer $TOKEN" | jq .
```

---

## 6. Reviewing Operational Readiness & Unresolved Blockers

At any point during the pilot, query the organization readiness scorecard:
```bash
curl -s -X GET http://localhost:8000/api/v1/agent/pilot/readiness \
  -H "Authorization: Bearer $TOKEN" | jq .
```

### Interpreting Readiness Scorecard Fields
- **`readiness_verdict`**:
  - `NO_GO`: One or more critical blockers are unresolved (e.g. read-only policy not acknowledged).
  - `CONDITIONAL_GO_REPLAY_PILOT`: Read-only policy acknowledged; verified for sanitized postmortem replay.
  - `GO_LIVE_PILOT`: Verified live VPC telemetry collector active (prohibited during replay pilot).
- **`blockers`**: Lists outstanding prerequisites (e.g. `Customer VPC live telemetry collector is not active`).
- **`provenance_breakdown`**: Confirms that live production customer incidents equal 0 and live telemetry is `NOT VERIFIED`.

---

## 7. Emergency Procedures & Administrative Kill-Switches

### Pausing Investigations (Emergency Kill-Switch)
If an anomaly occurs or the pilot must be halted immediately, activate the investigation pause switch:
```bash
curl -X POST http://localhost:8000/api/v1/agent/pilot/governance/policy \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "investigations_paused": true
  }'
```
Once paused, any new investigation request or in-flight Celery worker will immediately abort with `PermissionError: Incident investigations are paused for organization under pilot policy.`

### Disconnecting & Revoking Telemetry Integrations
If a telemetry integration endpoint must be disabled:
```bash
curl -X POST http://localhost:8000/api/v1/agent/pilot/integrations/{INTEGRATION_ID}/disconnect \
  -H "Authorization: Bearer $TOKEN"
```
The integration status transitions to `REVOKED`, and it is immediately excluded from any query execution.

### Cascading Data Retention Purge
At the conclusion of the pilot or upon customer request, completely purge all organization pilot data:
```bash
curl -X POST http://localhost:8000/api/v1/agent/pilot/governance/purge \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "confirm_organization_id": "customer_pilot_org",
    "purge_all_pilot_data": true
  }' | jq .
```

**Guarantees of Data Purge:**
1. **Server-Side Enforcement:** Confirmation ID must strictly match authenticated `org_id`; mismatched IDs fail immediately with HTTP 400.
2. **Cascading Tenant Scoping:** Deletes only investigations, repairs, feedback, and telemetry belonging to `customer_pilot_org`.
3. **Multi-Tenant Protection:** Other tenant records are completely unaffected.
4. **Anti-Recreation Invariant:** Workers executing in-flight tasks cannot re-insert purged data upon completion.
5. **Idempotency:** Re-running the purge request is completely safe and returns success with 0 deleted records.
