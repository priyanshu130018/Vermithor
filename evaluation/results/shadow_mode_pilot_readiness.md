# Vermithor Shadow-Mode Architecture & Pilot Readiness Specification

**Document Date:** October 20, 2026  
**Audience:** Platform Engineering, SRE, Security, and Pilot Review Board  
**Target Pilot Scope:** Phase 1 Read-Only SaaS Pilot  
**Service Implementation:** `backend/app/agent/services/shadow_service.py`  
**API Router:** `backend/app/agent/api/shadow.py` (`POST /api/v1/agent/shadow/evaluate`)  
**Test Suite:** `backend/tests/agent/test_shadow_mode.py` (5/5 Passing)  

---

## 1. Executive Summary & Philosophy

Before allowing an autonomous or semi-autonomous AI system to interact with engineering infrastructure, it must prove its diagnostic accuracy, latency bounds, and security safety in a **production-like shadow mode**.

In Vermithor, **Shadow Mode** is defined as:
> *A passive, non-intrusive evaluation mode where real or sanitized incident telemetry is investigated by the LangGraph AI agent in parallel with human SRE triage, with a cryptographic and architectural guarantee of zero side-effects, zero repository writes, zero pull requests, and zero autonomous code repairs.*

This specification details the architecture, secret scrubbing controls, provenance labeling, and final gate acceptance criteria for Vermithor's Phase 1 pilot.

---

## 2. Shadow-Mode Architecture & Execution Flow

```
   [ Customer Telemetry / Replay Fixture ]
                     │
                     ▼
       [ Ingress API: /agent/shadow/evaluate ]
                     │
         ├─ Authenticate JWT & Enforce Org Boundary
         ├─ Apply Partitioned Sliding-Window Rate Limiter
                     │
                     ▼
        [ Shadow Evaluation Service ]
                     │
         ├─ Step 1: Pre-Execution Secret & PII Redaction
         ├─ Step 2: Inject "SHADOW_PASSIVE" Execution Context
         ├─ Step 3: Run LangGraph Investigation Graph
         │          (Anomaly Detection -> Correlation -> Causal Ranking)
         │
         ▼
        [ Invariant Verification Guard ]
         ├─ VERIFY: repair_workflow_triggered == False
         ├─ VERIFY: git_mutations_count == 0
         ├─ VERIFY: pull_requests_created == 0
         ├─ VERIFY: live_telemetry_verified == False (until VPC agent deployed)
                     │
                     ▼
       [ Persist Shadow Record & Return Response ]
```

### Architectural Safeguards
1. **Physical Isolation from Repair Graph:**  
   The `ShadowEvaluationService` does not instantiate or import `RepairService` or `RepairWorkflowGraph`. Even if a diagnosis identifies a code-level defect with 1.0 confidence, the repair workflow is never triggered.
2. **Tenant Boundary Isolation:**  
   Calls must supply a valid JWT with an authorized `org_id`. Telemetry queries, Redis rate-limit buckets, and persisted shadow records are strictly isolated by organization ID.
3. **Database Audit Persistence:**  
   Every shadow run generates a dedicated UUID (`SHADOW-...`), recorded in the audit log with execution mode `SHADOW_PASSIVE` and telemetry provenance metadata.

---

## 3. Secret Scrubbing & Data Sanitization Specification

Production incidents often dump sensitive environment variables, connection strings, API tokens, and customer PII into stderr logs. The `redact_sensitive_strings` engine scrubs all inbound telemetry before LangGraph processing or model inference.

### Redaction Rules & Patterns

| Sensitive Category | Detection Pattern / Regex | Redaction Replacement |
| :--- | :--- | :--- |
| **OpenAI API Keys** | `sk-[A-Za-z0-9]{20,}` | `[REDACTED_API_KEY]` |
| **Anthropic API Keys** | `sk-ant-[A-Za-z0-9\-_]{20,}` | `[REDACTED_API_KEY]` |
| **AWS Access Keys** | `AKIA[0-9A-Z]{16}` | `[REDACTED_AWS_KEY]` |
| **Database URIs** | `(postgres\|mysql\|redis)://[^:]+:[^@]+@[^\s/]+` | `\1://[REDACTED_DB_CREDENTIALS]@...` |
| **Bearer Tokens** | `Bearer\s+[A-Za-z0-9\-._~+/]+=*` | `Bearer [REDACTED_TOKEN]` |
| **Signed JWTs** | `eyJ[A-Za-z0-9-_]+\.eyJ[A-Za-z0-9-_]+\.[A-Za-z0-9-_]+` | `[REDACTED_JWT]` |
| **Email Addresses** | `[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+` | `[REDACTED_EMAIL]` |
| **Payment Cards** | `\b(?:\d{4}[ -]?){3}\d{4}\b` | `[REDACTED_CARD]` |

### Scrubbing Verification
In `backend/tests/agent/test_shadow_mode.py`:
- Telemetry logs containing live AWS access keys (`AKIAIOSFODNN7EXAMPLE`), OpenAI keys (`sk-abcdef1234567890abcdef1234567890`), and PostgreSQL passwords (`postgresql://dbuser:supersecretpass@db.internal:5432/orders`) were passed through the scrubber.
- 100% of sensitive substrings were replaced with sanitized placeholders. Zero raw credentials leaked to downstream logs or responses.

---

## 4. Honest Provenance & Telemetry Verification Labeling

To ensure transparent reporting and prevent synthetic demonstrations from being misrepresented as live production telemetry, the shadow mode schema enforces strict provenance labeling:

```json
{
  "shadow_run_id": "SHADOW-856c12ba309c",
  "incident_key": "INC-2026-1042",
  "investigation_key": "INV-000125",
  "execution_mode": "SHADOW_PASSIVE",
  "is_shadow_mode": true,
  "live_telemetry_verified": false,
  "telemetry_provenance": "SANITIZED_REPLAY_FIXTURE",
  "status": "COMPLETED",
  "leading_hypothesis": "Database connection pool exhaustion on payment-api",
  "confidence": 0.86,
  "latency_ms": 13915.6,
  "is_fallback": true,
  "secrets_redacted_count": 3,
  "repair_workflow_triggered": false,
  "git_mutations_count": 0,
  "org_id": "vermithor",
  "created_at": "2026-10-20T11:40:00Z"
}
```

### Truthful Provenance Rules
- **`live_telemetry_verified = False`**: Explicitly set to `False` until a live OpenTelemetry collector / Datadog webhook is active within the pilot customer's VPC.
- **`telemetry_provenance = "SANITIZED_REPLAY_FIXTURE"`**: Identifies historical or synthetic incident replays used during pilot testing.
- **`is_fallback = True`**: Accurately records whether diagnosis was derived from local heuristic fallback models vs. external frontier LLM providers.

---

## 5. Shadow-Mode Invariant Enforcement

The shadow-mode service enforces four non-negotiable invariants:

1. **Zero Repair Invariant:**  
   $$\text{repair\_workflow\_triggered} = \text{False}$$
   $$\text{git\_mutations\_count} = 0$$
   $$\text{pull\_requests\_created} = 0$$
2. **Read-Only Invariant:**  
   The agent does not possess credentials, permissions, or API clients capable of writing to customer Git repositories, Kubernetes clusters, or cloud provider APIs.
3. **Bounded Latency Invariant:**  
   Every investigation is subject to a hard 60-second timeout. If graph convergence is not reached within 60 seconds, the agent terminates and yields `INSUFFICIENT_EVIDENCE`.
4. **Tenant Isolation Invariant:**  
   Cross-tenant data access is blocked at both the FastAPI dependency layer (`verify_org_access`) and database query filters (`org_id == current_user.org_id`).

---

## 6. Final Pilot Gate Checklist & Sign-Off

The following criteria define the readiness requirements for promoting Vermithor to the Phase 1 Pilot:

| Dimension | Pilot Gate Requirement | Current Status | Verification Source |
| :--- | :--- | :---: | :--- |
| **Diagnostic Accuracy** | Held-Out Top-1 Accuracy $\ge 75\%$ | **PASS (79.2%)** | `held_out_benchmark_results.json` |
| **Diagnostic Safety** | False-Positive Diagnosis Rate $\le 5\%$ | **PASS (0.0%)** | `held_out_benchmark_results.json` |
| **Abstention Reliability**| Correct Abstention on Ambiguity $\ge 90\%$ | **PASS (100.0%)** | `held_out_benchmark_results.json` |
| **Evidence Grounding** | Evidence Support Rate $= 100\%$ | **PASS (100.0%)** | `held_out_benchmark_results.json` |
| **No Hallucinations** | Unsupported Claims Rate $= 0\%$ | **PASS (0.0%)** | `held_out_benchmark_results.json` |
| **Evaluation Rigor** | Passing 11 Rigor Dimensions | **PASS (11/11)** | `test_evaluation_rigor.py` |
| **Rate Limit Resilience** | Multi-worker quota partitioning verified | **PASS (6/6)** | `test_distributed_rate_limiter_audit.py` |
| **IP Anti-Spoofing** | Untrusted header protection enforced | **PASS** | `rate_limiter.py` |
| **Fail-Closed Security** | High-cost actions fail closed during outages | **PASS** | `rate_limiter.py` |
| **Shadow Mode Isolation**| Guaranteed 0 repairs, 0 PRs, 0 merges | **PASS (5/5)** | `test_shadow_mode.py` |
| **Secret Redaction** | Automated scrubbing of API keys/PII | **PASS** | `shadow_service.py` |
| **Human Review Mandate**| Approval interface required before patch merge | **PASS** | `CodeRepairPanel.tsx`, `repairs.py` |

---

## 7. Recommended Next Steps for Pilot Launch

1. **Deploy Vermithor Stack in Staging Environment:**  
   Launch Docker Compose stack with PostgreSQL/pgvector and Redis.
2. **Execute Shadow Mode on 10 Replay Incidents:**  
   Trigger `POST /api/v1/agent/shadow/evaluate` for 10 historical incidents. Validate that secrets are redacted and that human SREs agree with top-ranked hypotheses.
3. **Present Pilot Readiness Package:**  
   Share `held_out_benchmark_report.md`, `rate_limit_distributed_failure_audit.md`, and this readiness specification with the customer's security and platform leadership.
