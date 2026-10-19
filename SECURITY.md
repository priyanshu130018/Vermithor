# Vermithor — Security Policy & Architecture

This document defines the security architecture, threat model, trust boundaries, vulnerability reporting procedure, and credential management standards for the **Vermithor** AI Production Incident Intelligence Platform.

---

## 1. Security Architecture & Trust Boundaries

```text
               [ UNTRUSTED ZONE: Public Internet / Browsers ]
                                     │
                                     ▼ (TLS Termination / Ingress)
                      ┌──────────────┴──────────────┐
                      │                             │
                      ▼ (Public UI Assets)          ▼ (Strict JWT Authentication)
            [ Frontend (React SPA) ]       [ API Gateway (Nginx :8080) ]
            - No Secrets / No Keys         - Reverse Proxy & Rate Limiting (30/10/2 r/s)
            - VITE_API_BASE_URL only       - 10MB Body Cap & Method Restrictions
                                           - Security Headers & Request-ID Tracing
                                                    │
                      ┌─────────────────────────────┴─────────────────────────────┐
                      ▼ (Internal Private Kubernetes ClusterIP / NetworkPolicies) ▼
        [ Backend Modular Monolith (:8000) ]                     [ PostgreSQL & Redis ]
        - Non-Root & Capabilities Dropped                       - Private ClusterIP
        - PII & Secret Log Redaction                            - Encrypted Persistent Storage
```

---

## 2. Authentication & Cryptographic JWT Policy

- **Algorithm Pinning**: The FastAPI backend natively enforces HMAC-SHA256 (`HS256`) via `backend/app/common/security.py`. Tokens using `none`, `RS256`, or alternative algorithms are rejected immediately to prevent algorithm confusion attacks.
- **Claim Enforcement**: All tokens must carry valid:
  - `iss` (Issuer, default: `vermithor`)
  - `aud` (Audience, default: `vermithor-api`)
  - `exp` (Expiration timestamp)
  - `iat` / `nbf` (Issued-at / Not-before timestamps with $\le 30$ seconds clock skew tolerance)
- **Generic Error Responses**: Authentication failures return sanitized envelopes (`{"error": "unauthorized", "message": "Invalid authentication token", "request_id": "..."}`) without exposing stack traces, crypto errors, or internal state.
- **Frontend Token Isolation**: The React client stores session tokens issued by trusted identity providers. In-browser dev token generation is strictly restricted to local development environments (`import.meta.env.DEV`).

---

## 3. Secret Management Lifecycle

- **Zero Git Secrets**: Version control must never contain production database passwords, JWT signing keys, or LLM API keys.
- **Externalized Injection (`existingSecret`)**: In production Kubernetes deployments, secrets are provisioned out-of-band (e.g. via SealedSecrets, External Secrets Operator, or HashiCorp Vault) and attached to Helm releases:
  ```yaml
  secrets:
    existingSecret: vermithor-production-secrets
  ```
- **Manual Provisioning Example**:
  ```bash
  kubectl create secret generic vermithor-production-secrets \
    --namespace vermithor \
    --from-literal=JWT_SECRET='<MIN_32_CHAR_CRYPTO_RANDOM_KEY>' \
    --from-literal=DATABASE_URL='postgresql+psycopg://neondb_owner:<NEON_PASSWORD>@ep-lingering-scene-49972255-pooler.us-east-2.aws.neon.tech/neondb?sslmode=require' \
    --from-literal=DATABASE_URL_UNPOOLED='postgresql+psycopg://neondb_owner:<NEON_PASSWORD>@ep-lingering-scene-49972255.us-east-2.aws.neon.tech/neondb?sslmode=require' \
    --from-literal=REDIS_URL='redis://redis:6379/0'
  ```

---

## 4. Kubernetes & Container Security Baseline

- **Least-Privilege Pods**: Workloads enforce:
  - `runAsNonRoot: true`
  - `allowPrivilegeEscalation: false`
  - `capabilities: { drop: ["ALL"] }`
  - `automountServiceAccountToken: false` (prevents lateral API server reconnaissance).
- **Network Isolation**: Kubernetes `NetworkPolicies` enforce a default-deny posture, allowing only:
  - UDP/TCP Port 53 egress to `kube-dns` for CoreDNS service discovery.
  - Ingress from `gateway` to backend modular monolith.
  - Authorized point-to-point backend service communications.
- **Internal Storage & Infrastructure**: PostgreSQL and Redis are bound exclusively to `ClusterIP` services and are inaccessible from external ingress routes.

---

## 5. Security Threat Model

| Threat | Risk Level | Primary Mitigations |
| :--- | :--- | :--- |
| **Unauthenticated API Access** | Critical | Gateway HMAC-SHA256 JWT validation with algorithm pinning |
| **Credential / Secret Leakage** | Critical | Externalized Kubernetes secret injection, automated CI scans |
| **API Denial of Service (DoS)** | High | Tiered Nginx rate limiting (30/10/2 r/s) & 10MB body limits |
| **Cross-Site Scripting (XSS)** | High | React automated DOM escaping, Strict CSP & `X-XSS-Protection` |
| **Clickjacking / Framing** | Medium | `X-Frame-Options: DENY` & `frame-ancestors 'none'` CSP |
| **MIME-Type Confusion** | Medium | `X-Content-Type-Options: nosniff` header |
| **Algorithm Confusion (JWT)** | Critical | Explicit `alg == "HS256"` header validation |
| **Lateral Pod Movement** | High | Default-deny `NetworkPolicies` & disabled service account tokens |
| **Container Privilege Escalation** | High | `runAsNonRoot`, non-privileged execution, dropped capabilities |
| **Vulnerable Dependencies** | Medium | Automated Trivy container scans and `npm audit` / `pip-audit` CI |

---

## 6. Secret Rotation Runbook

In the event of a suspected or scheduled credential rotation:

1. **Generate New Cryptographic Key**:
   ```bash
   NEW_JWT_SECRET=$(openssl rand -base64 32)
   ```
2. **Update Kubernetes Production Secret**:
   ```bash
   kubectl create secret generic vermithor-production-secrets \
     --namespace vermithor \
     --from-literal=JWT_SECRET="${NEW_JWT_SECRET}" \
     --dry-run=client -o yaml | kubectl apply -f -
   ```
3. **Trigger Rolling Restart of Gateway & Services**:
   ```bash
   kubectl rollout restart deployment/gateway -n vermithor
   kubectl rollout restart deployment/vermithor-backend -n vermithor
   ```
4. **Invalidate Old Client Sessions**: Re-issue user session tokens signed with the new secret.

---

## 7. Reporting a Security Vulnerability

If you discover a potential security vulnerability in Vermithor:
- **Do NOT open a public GitHub issue.**
- Email the Vermithor Security Team at `security@vermithor.local` with detailed reproduction steps, potential impact, and suggested remediations.
- All valid disclosures receive an acknowledgment within 24 hours.
