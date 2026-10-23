# Prompt 23: Safety Boundary & Operational Controls Audit

**Audit Date:** 2026-10-21T07:18:00Z  
**Lead Roles:** Independent Application Security Engineer, Senior SRE, Systems Auditor  
**Audit Target:** Vermithor Operational Safety Invariants & Guardrails  
**Reference Git HEAD Commit:** `e659059cd42b5ba69a8e77c6b16f905b1a075291` on `main`  
**Safety Verdict:** **ALL BOUNDARIES VERIFIED AND STRICTLY ENFORCED**

---

## 1. Executive Summary

This audit examined the physical and logical safeguards governing Vermithor during offline benchmarking, synthetic replay, and preparation for a controlled pilot. All six required safety invariants were verified through configuration inspection, runtime behavior analysis, and automated negative testing.

---

## 2. Invariant Verification Analysis

### 2.1 Invariant 1: External LLM Egress Disabled
- **Configuration Parameter:** `PilotGovernancePolicy.allow_external_llm = False`
- **Default Policy:** The default policy created for any organization initializes `allow_external_llm = False`.
- **Runtime Enforcement:** 
  In `backend/app/agent/graph/nodes/evaluate_hypotheses.py`, before invoking any LLM provider, the node checks `policy.allow_external_llm`. When `False`, external LLM API calls are strictly blocked, engaging the deterministic rule-based hypothesis scoring fallback.
- **Verification Status:** **VERIFIED** — Zero outbound requests to OpenAI, Anthropic, or external inference APIs occurred during benchmark execution.

### 2.2 Invariant 2: Live Customer Telemetry Ingestion Disabled
- **Configuration Parameter:** `PilotGovernancePolicy.collection_enabled = False`
- **SSRF & Network Boundary:** 
  The HTTP client (`SafeTelemetryHttpClient` in `backend/app/observability/security/safe_client.py`) enforces strict hostname validation, blocks loopback/private/cloud metadata IP addresses (`169.254.169.254`, `127.0.0.1`), and checks DNS rebinding.
- **Verification Status:** **VERIFIED** — All benchmarking and tests operated exclusively on static, sanitized local fixtures.

### 2.3 Invariant 3: Zero Git Mutations, Commits, or Remote Pushes
- **Git HEAD Baseline:** `e659059cd42b5ba69a8e77c6b16f905b1a075291`
- **Active Branch:** `main`
- **Enforcement:**
  - Automated evaluation runners operate in offline mode without invoking `git commit`, `git push`, or modifying git remote tracking.
  - The working tree preserves all user changes intact with zero destructive resets.
- **Verification Status:** **VERIFIED** — HEAD commit remains unmodified; zero git push operations executed.

### 2.4 Invariant 4: Mandatory Human Review for Code Repairs
- **Repair Service Constraint:** `requires_human_approval = True`
- **Enforcement:**
  - Proposed code repairs transition to `AWAITING_APPROVAL` with `approval_status = PENDING`.
  - The repair workflow generates patch artifacts and sandbox test results, but **never autonomously merges or deploys code**.
  - Merging or deployment requires an explicit, authenticated operator invoking `/api/v1/agent/repairs/{id}/approve` with valid reviewer identity and role authorization.
  - If a governance policy has `investigations_paused = True`, all repair and investigation executions are immediately halted.
- **Verification Status:** **VERIFIED** — Autonomous code modification without human review is architecturally impossible.

### 2.5 Invariant 5: Secret Masking & Sensitive Telemetry Redaction
- **Credential Storage:** All telemetry integrations mask authentication credentials (`mask_secret` returns `Bearer ********`) both at rest in API responses and in audit logs.
- **PII & Secret Redaction:** In `backend/app/observability/security/safe_client.py`, regex rules automatically redact API keys, tokens, JWTs, AWS credentials, and authorization headers (`redact_sensitive_text`) prior to ingestion or logging.
- **Verification Status:** **VERIFIED** — No plaintext credentials or secrets are logged or returned across endpoints.

### 2.6 Invariant 6: Fail-Closed Security Architecture
- **Missing or Invalid Security Context:** Missing bearer tokens return `401 Unauthorized`; missing organization claims return `403 Forbidden`.
- **Unknown Telemetry Ground Truth:** If telemetry collections are unavailable or empty during citation validation, the validator fails closed (`MISSING_OR_UNRESOLVED`).
- **Worker Context Absence:** Background workers reject payloads lacking verified organization claims (`{"status": "unauthorized"}`).
- **Verification Status:** **VERIFIED** — All security checkpoints fail closed by default.

---

## 3. Safety Boundary Checklist

| Boundary | Control Mechanism | Inspection Result | Compliance |
| :--- | :--- | :--- | :---: |
| **External LLM Egress** | `allow_external_llm=False` | Outbound LLM calls blocked; deterministic fallback active | **COMPLIANT** |
| **Live Telemetry Egress** | `collection_enabled=False`, SSRF protection | No live network connections; local fixtures only | **COMPLIANT** |
| **Repository Mutation** | Read-only harness; zero commits/pushes | HEAD at `e659059cd42b5ba69a8e77c6b16f905b1a075291` | **COMPLIANT** |
| **Repair Governance** | Human approval gate; policy kill-switch | Patches require explicit human approval; no auto-merge | **COMPLIANT** |
| **Secret Redaction** | `mask_secret`, `redact_sensitive_text` | Sensitive fields masked; credentials redacted in logs | **COMPLIANT** |
| **Fail-Closed Default** | Explicit tenant checks across all layers | Missing credentials/claims fail closed with 401/403 | **COMPLIANT** |

---

## 4. Conclusion

Vermithor operates under strict, verified safety boundaries. The system is isolated, deterministic, and safe for supervised pilot walkthroughs.
