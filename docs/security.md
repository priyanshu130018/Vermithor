# Vermithor Security Architecture

Vermithor implements defense-in-depth security principles across the API gateway, microservice runtime, database layer, and container orchestrator.

---

## 1. Gateway Security Boundary (OpenResty / Lua)

The API Gateway (`gateway/`) acts as the perimeter security barrier for all incoming client traffic:

1. **JWT Verification (Lua `jwt_auth.lua`)**:
   - Validates HMAC-SHA256 (HS256) signatures using `JWT_SECRET`.
   - Rejects unsigned requests or tokens using forbidden algorithms (e.g. `none`, `RS256` mismatch).
   - Validates standard RFC 7519 claims:
     - `iss` (Issuer) must match `vermithor`.
     - `aud` (Audience) must match `vermithor-api`.
     - `exp` (Expiration time) must be in the future.
     - `nbf` (Not Before) and `iat` (Issued At) bounds validation.
   - Public endpoint exceptions: `/health` and Prometheus `/metrics` bypass JWT requirements for orchestrator probe access.
2. **Rate Limiting (Nginx `limit_req_zone`)**:
   - Enforces a 100 requests/second burst ceiling per client IP with a shared 10MB memory zone (`rate=100r/s burst=200 nodelay`).
   - Automatically returns standard `429 Too Many Requests` status upon violation.
3. **HTTP Security Headers**:
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`
   - `X-XSS-Protection: 1; mode=block`
   - `Strict-Transport-Security: max-age=31536000; includeSubDomains` (when TLS enabled)
   - `Content-Security-Policy: default-src 'self'`
4. **Upstream Request Timeouts**:
   - Connection timeout: 5s.
   - General API timeout: 15s.
   - Summary generation timeout: 130s (accommodating local LLM inference).

---

## 2. Secrets Management & Environment Isolation

- **Zero Hardcoded Secrets**: Passwords, encryption keys, and tokens are injected via environment variables.
- **Root `.env` for Local Development**: Server secrets are consolidated in `Vermithor/.env` and excluded from git via `.gitignore`.
- **Frontend Isolation**: Browser-facing code in `frontend/` contains only public `VITE_` variables (`VITE_API_BASE_URL`). No backend secrets or database credentials are included in client bundles.
- **Kubernetes Secrets**: Secrets in Kubernetes are decoupled into `infrastructure/helm/vermithor/templates/secrets.yaml` with support for external secret operators.

---

## 3. Container & Kubernetes Hardening

1. **Non-Root Execution**:
   - Application containers define unprivileged runtime user IDs (`runAsNonRoot: true`, `runAsUser: 10001`).
2. **Read-Only Root Filesystems**:
   - Microservices execute with read-only root filesystems, mounting ephemeral `/tmp` volumes only when temporary scratch storage is required.
3. **Network Policies**:
   - Strict ingress/egress firewalling between Kubernetes namespaces and pods prevents unauthorized lateral movement.
