# Prompt 24 Operational Safety Boundary Matrix

**Roles:** Application Security Engineer, Senior SRE, Compliance Auditor  
**Project:** Vermithor  
**Baseline Commit:** `e659059cd42b5ba69a8e77c6b16f905b1a075291`  
**Timestamp:** 2026-10-21T08:52:00Z  
**Status:** ALL PILOT SAFETY BOUNDARIES ENFORCED  

---

## 1. Safety Boundary Matrix Overview

This document establishes the operational boundaries, data governance constraints, and execution safeguards governing Vermithor's supervised sanitized-replay pilot. Every control has been classified under one of three rigorous status tags:

- **`TESTED`**: Actively exercised and verified passing by automated unit, integration, or regression test execution during this audit.
- **`CODE_INSPECTED`**: Directly audited and confirmed by reviewing source code, configuration schema, and architectural call-graphs.
- **`NOT_VERIFIED`**: Identified as out of scope, unexercised, or requiring live customer deployment (strictly prohibited in this pilot).

---

## 2. Complete Safety Control Matrix

| ID | Operational Safety Boundary | Implementation / Enforcement Mechanism | Verification Method | Status Tag | Evidence / Test Reference |
| :---: | :--- | :--- | :--- | :---: | :--- |
| **SB-01** | **Offline Replay Execution** | All replay incidents execute against static, sanitized fixture sets. No live network ingress/egress. | Automated benchmark execution in isolated SQLite in-memory environment | **`TESTED`** | [run_blind_evaluation.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/evaluation/run_blind_evaluation.py), [run_prompt21_held_out.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/evaluation/run_prompt21_held_out.py) |
| **SB-02** | **Zero Live Customer Telemetry** | No real customer Prometheus endpoints, Jaeger collectors, or Kubernetes APIs are polled or queried. | Telemetry client mocked/sandboxed with fixture data; zero socket connections | **`TESTED`** | [test_pilot_onboarding_and_readiness.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/tests/agent/test_pilot_onboarding_and_readiness.py#L45-L70) |
| **SB-03** | **Zero External LLM Egress** | `allow_external_llm=False`; deterministic grounded fallback and local HuggingFace/Ollama mock providers only. | Network sockets blocked during test runs; external API keys unset | **`TESTED`** | [test_prompt22_adversarial_suite.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/tests/agent/test_prompt22_adversarial_suite.py#L120-L145) |
| **SB-04** | **Human-in-the-Loop Repair Review** | AI repair patches are proposed as read-only unified diffs. Autonomous git commit, push, merge, or deployment is strictly blocked. | `/repairs/{id}/approve` endpoint records human decisions; no autonomous write operations exist in repository provider | **`TESTED`** | [test_repair_api.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/tests/agent/test_repair_api.py#L80-L115), [repair_service.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/app/agent/services/repair_service.py#L380-L390) |
| **SB-05** | **Read-Only Pilot Flag Enforcement** | Investigation and repair responses explicitly return `is_read_only_pilot=True` and omit push/deploy triggers. | Response schema verification on all investigation and repair endpoints | **`TESTED`** | [CodeRepairPanel.test.tsx](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/frontend/src/__tests__/CodeRepairPanel.test.tsx), [test_prompt23_security_regression.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/tests/agent/test_prompt23_security_regression.py#L50-L75) |
| **SB-06** | **Multi-Tenant Organization Scoping** | All database queries, Celery tasks, and API routes strictly filter by validated JWT `org_id`. | Cross-tenant data leakage and access tests | **`TESTED`** | [test_prompt24_production_configuration.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/tests/agent/test_prompt24_production_configuration.py#L15-L65) |
| **SB-07** | **Production Allowlist Fail-Closed** | In production (`APP_ENV=production`), test fixture orgs (`org_alpha`, `org_beta`) are forbidden; only explicit orgs permitted. | Settings-driven allowlist verification in production mode | **`TESTED`** | [test_prompt24_production_configuration.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/tests/agent/test_prompt24_production_configuration.py#L50-L85) |
| **SB-08** | **Worker-Side Tenant Verification** | Celery tasks abort if task payload lacks an authorized org or if investigation record tenant mismatches payload org. | Celery task invocation tests with mismatched/missing org payloads | **`TESTED`** | [test_prompt24_production_configuration.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/tests/agent/test_prompt24_production_configuration.py#L90-L130) |
| **SB-09** | **Administrative Kill-Switch** | Pilot governance policy allows instant pausing of investigations and repairs per organization (`investigations_paused=True`). | Policy enforcement in API routes and worker tasks | **`TESTED`** | [test_prompt23_security_regression.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/tests/agent/test_prompt23_security_regression.py#L140-L165) |
| **SB-10** | **Credential & PII Secret Redaction** | Database URLs, API tokens, passwords, and private SSH keys are scrubbed before prompt synthesis or logging. | Regex and diagnostic redaction tests | **`TESTED`** | [test_prompt22_adversarial_suite.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/tests/agent/test_prompt22_adversarial_suite.py#L40-L65), [config.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/app/common/config.py#L27-L65) |
| **SB-11** | **SSRF Prevention & DNS Pinning** | Webhook and git repository URLs validated against private IP ranges, decimal/octal encodings, and DNS rebinding. | SSRF URL validator unit tests | **`TESTED`** | [test_adversarial_security_audit.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/tests/agent/test_adversarial_security_audit.py#L90-L130) |
| **SB-12** | **Cascading Tenant Retention Purge** | Deleting an organization or investigation record cascades only within tenant boundary without touching other tenants. | Deletion endpoint and database foreign key verification | **`TESTED`** | [test_investigation_api.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/tests/agent/test_investigation_api.py#L180-L210) |
| **SB-13** | **Stale Patch Tampering Prevention** | Approval endpoint requires `expected_patch_hash` matching the database record patch SHA-256 before approval succeeds. | Approval tamper injection test | **`TESTED`** | [test_prompt23_security_regression.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/tests/agent/test_prompt23_security_regression.py#L90-L115) |
| **SB-14** | **Inbound Rate Limiting & Degraded Partitioning** | Sliding window rate limiting bounds ingress traffic; in degraded mode without Redis, in-memory limits are subdivided by worker count. | Rate limiter unit tests and middleware inspection | **`CODE_INSPECTED`** | [rate_limiter.py](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/backend/app/common/rate_limiter.py#L40-L95) |
| **SB-15** | **Live Production Telemetry Ingestion** | Connecting to customer AWS CloudWatch, Datadog, or live OpenTelemetry pipelines. | Prohibited by design for sanitized replay pilot. Not authorized. | **`NOT_VERIFIED`** | Customer Pilot Agreement Section 3.1 |
| **SB-16** | **Live Automated Code Push to Customer Repos** | Creating git branches or opening pull requests on live customer GitHub/GitLab repositories. | Prohibited by design. Local provider and read-only mode only. | **`NOT_VERIFIED`** | Customer Pilot Agreement Section 3.2 |

---

## 3. Boundary Verification Summary

- **Total Controls Evaluated:** 16
- **Controls Confirmed `TESTED`:** 13 (81.25%)
- **Controls Confirmed `CODE_INSPECTED`:** 1 (6.25%)
- **Controls Confirmed `NOT_VERIFIED` (Strictly Excluded from Pilot Scope):** 2 (12.50%)

### Compliance Statement
Vermithor complies with all mandatory pre-pilot safety controls. Under no circumstances may controls SB-15 (Live Telemetry Ingestion) or SB-16 (Live Code Push) be activated without explicit re-certification and mutual customer authorization.
