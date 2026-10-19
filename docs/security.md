# Vermithor Security Architecture & Compliance

This document details the security principles, authentication contracts, secret handling, database transport security, AI guardrails, and compliance posture implemented across the **Vermithor** platform.

---

## 1. Perimeter Security & JWT Authentication (Nginx Gateway & FastAPI)

The standard Nginx API Gateway (`gateway/`, `nginx:alpine`) acts as the reverse proxy, rate limiting, and security header boundary for all external traffic, forwarding requests to the FastAPI modular monolith backend where native JWT validation (`backend/app/common/security.py`) enforces strict cryptographic checks.

### 1.1 Cryptographic JWT Verification Contract (`backend/app/common/security.py`)
Every client request targeting protected `/api/v1/*` endpoints must provide a valid JSON Web Token (JWT) in the HTTP `Authorization` header:

```text
Authorization: Bearer <JWT_STRING>
```

FastAPI validates the token prior to executing any protected route handler:

1. **Strict Algorithm Pinning**:
   - Only HMAC-SHA256 (`HS256`) is permitted.
   - Tokens specifying `alg: "none"`, `RS256`, or other asymmetric schemes are rejected immediately with `HTTP 401 Unauthorized`.
2. **Signing Secret Management**:
   - The cryptographic signature is validated against the environment variable `JWT_SECRET`.
   - Insecure hardcoded secret fallbacks have been removed. If `JWT_SECRET` is missing or empty, the gateway logs a critical warning and returns `HTTP 401`.
3. **Mandatory RFC 7519 Claims Enforcement**:
   - **Subject (`sub`)**: Must be present and non-empty.
   - **Issuer (`iss`)**: Must strictly match `JWT_ISSUER` (default: `vermithor`).
   - **Audience (`aud`)**: Must strictly match `JWT_AUDIENCE` (default: `vermithor-api`).
   - **Expiration (`exp`)**: Must be a valid numeric timestamp in the future.
   - **Clock Skew Tolerance**: Tolerates up to $\pm 30$ seconds of clock drift (`CLOCK_SKEW_TOLERANCE_SECONDS = 30`) across `exp`, `nbf` (Not Before), and `iat` (Issued At) claims to accommodate distributed cluster time discrepancies.
4. **Information Leakage Prevention**:
   - When authentication fails, the gateway logs internal failure reasons (e.g. `[AUTH_FAILURE] reason=Token expired`) to internal logs for operator auditing, while returning a generic, non-leaking JSON error payload to the client:
     ```json
     {
       "error": "unauthorized",
       "message": "Invalid authentication token",
       "request_id": "<REQUEST_UUID>"
     }
     ```
5. **Upstream Identity Propagation**:
   - Upon successful verification, the gateway injects trusted identity headers upstream:
     - `X-User-ID`: The validated `sub` claim.
     - `X-Authenticated`: Hardcoded to `"true"`.
     - `X-Request-ID`: The tracing request UUID.

### 1.2 Public vs. Protected Endpoints
- **Public (Bypass JWT)**:
  - `GET /health` (Gateway and backend orchestrator health probes).
  - `GET /metrics` (Prometheus metrics scraping).
- **Protected (Require Valid JWT)**:
  - All `/api/v1/*` routes (`/events`, `/incidents`, `/observations`, `/anomalies`, `/correlations`, `/rca`, `/logs`, `/retrieval`, `/runbooks`, `/summaries`).

### 1.3 Rate Limiting & DoS Defense
The gateway defines dedicated memory zones enforcing rate ceilings:
- `api_general`: 30 req/s, burst 20 (`nodelay`).
- `api_summary`: 2 req/s, burst 5 (`nodelay`) — protects against LLM compute exhaustion.
- `api_logs`: 10 req/s, burst 20 (`nodelay`).
- Exceeded limits trigger an immediate `HTTP 429 Too Many Requests` response with a `Retry-After: 5` header.

### 1.4 Hardened HTTP Security Headers
Every HTTP response emitted by the gateway includes modern defense headers:
- `X-Content-Type-Options: nosniff` (Prevents MIME-type sniffing).
- `X-Frame-Options: DENY` (Mitigates clickjacking attacks).
- `X-XSS-Protection: 1; mode=block` (Legacy browser XSS filter).
- `Referrer-Policy: strict-origin-when-cross-origin`.
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`.
- `Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; ...`.
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` (Conditionally active on HTTPS connections).

---

## 2. Secrets Management & Environment Isolation

### 2.1 Developer Environment Security
- **Version Control Exclusion**: Root `.env` and `.neon` metadata files are explicitly ignored in [`.gitignore`](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/.gitignore).
- **Template Hygiene**: [`.env.example`](file:///c:/Users/13ver/Desktop/New%20folder/project/Vermithor/.env.example) contains only non-sensitive placeholder tokens (`<NEON_PASSWORD>`, `<HF_TOKEN>`).
- **Frontend Code Isolation**: The React browser client bundle includes only public variables prefixed with `VITE_` (`VITE_API_BASE_URL`). Database credentials, server secrets, and API tokens are never referenced in client code.

### 2.2 Container Image Build Isolation
- `.dockerignore` files are maintained in the repository root, `backend/`, `frontend/`, and `gateway/`.
- Neither `.env`, local SQLite files, git histories, nor temporary build caches are copied into production images.
- Dockerfiles avoid using `ARG` or `ENV` instructions for secret passing. All sensitive credentials are provided dynamically at container startup via environment variables.

---

## 3. Database Transport Security (Neon PostgreSQL)

- **Mandatory TLS Encryption**: Remote communication with Neon Serverless PostgreSQL requires TLS encryption via `?sslmode=require` and `&channel_binding=require` query parameters.
- **Credential Protection**: SQLAlchemy engine configurations and database logs mask connection string credentials (`***`) during exception traces.
- **Connection Isolation**: Schema migrations utilize dedicated unpooled endpoints (`DATABASE_URL_UNPOOLED`) with non-persistent connections (`pool.NullPool`), preventing persistent connection leakage.

---

## 4. AI/ML & LLM Security Guardrails

### 4.1 Prompt Injection Defense
Unstructured incident logs and operator inputs are treated as untrusted data:
- Telemetry data injected into LLM prompts is strictly delimited within `<UNTRUSTED_TELEMETRY_DATA>` XML blocks.
- The system prompt explicitly instructs the LLM to ignore any instructions or directives embedded within telemetry payloads.

### 4.2 API Token Protection (`Hugging Face`)
- The Hugging Face API token (`HF_TOKEN`) is read strictly from environment configuration (`Settings.HF_TOKEN`).
- It is transmitted via HTTPS `Authorization: Bearer <HF_TOKEN>` headers to `https://router.huggingface.co/v1`.
- It is never serialized into database models, logged to stdout/stderr, or exposed in OpenAPI responses.

### 4.3 Programmatic Evidence Validation & Hallucination Defense
- The LLM is constrained to output structured JSON matching `IncidentSummaryGeneratedSchema` at low temperature ($0.1$).
- The `EvidenceValidator` service programmatically audits every evidence citation generated by the LLM against verified telemetry IDs (`valid_source_ids`).
- Fabricated or unobserved citations are automatically stripped, and an audit warning is recorded in the summary `limitations` block.

### 4.4 Automated Fallback Security
If Hugging Face is unreachable, unauthenticated (401), or rate-limited (429), the platform activates deterministic fallback synthesis (`is_fallback: true`) using verified RCA candidates, preventing outage cascades and unhandled exceptions.

---

## 5. Log Intelligence Sanitization & Data Privacy

Unstructured application logs ingested via `/api/v1/logs/process` undergo automated redaction before embedding generation or database storage:

| Sensitive Pattern | Sanitization Method | Sanitized Output Example |
|---|---|---|
| **JSON Web Tokens (JWT)** | Regex regex pattern match | `[REDACTED_JWT]` |
| **API Keys / Bearer Tokens** | Regex pattern match | `Bearer [REDACTED_TOKEN]` |
| **Passwords / Credentials** | Pattern matching key-value pairs | `password=[REDACTED_SECRET]` |
| **IPv4 & IPv6 Addresses** | IP regex masking | `<IP_ADDRESS>` |
| **UUIDs / User Identifiers** | Hex-string masking | `<UUID>` |
| **Timestamps** | Canonical normalization | `<TIMESTAMP>` |

---

## 6. Container Hardening & Network Isolation

### 6.1 Multi-Stage Docker Builds
- **Builder Stage**: Packages dependencies using compilers (`gcc`, `libpq-dev`).
- **Runtime Stage**: Copies precompiled wheels into a minimal `python:3.12-slim` image and purges build tools, reducing the Common Vulnerabilities and Exposures (CVE) surface.

### 6.2 Non-Root Execution
- Backend container runs under an unprivileged system user (`appuser`, UID `appuser`, `/sbin/nologin`).
- Nginx containers drop capabilities where supported.

### 6.3 Network Isolation
- Docker Compose defines a private bridge network (`vermithor-network`).
- Internal microservices communicate exclusively across the internal container network without exposing backend ports (8000, 6379) to public interfaces.
- Host port mappings are restricted to `127.0.0.1` for Redis (`127.0.0.1:6379:6379`) to prevent unauthorized local network exposure.

---

## 7. Security Gaps & Unverified Controls

The following controls represent architectural limitations or planned enterprise enhancements:

| Control | Implementation Status | Notes |
|---|---|---|
| **External IdP (OIDC / OAuth2)** | `PLANNED` | Current backend relies on pre-issued HS256 tokens. Integration with enterprise identity providers (Keycloak, Auth0, Okta) is planned. |
| **Fine-Grained Role-Based Access (RBAC)** | `PLANNED` | Backend verifies authenticated subject validity; role-level permission checking (e.g. SRE Admin vs. Read-Only) is not yet enforced in backend route dependencies. |
| **Direct KMS / Vault Syncing** | `UNVERIFIED` | Production Helm charts support `existingSecret`; daemonized secret synchronizers (HashiCorp Vault Agent, AWS Secrets Store CSI) remain unverified in the local repository. |
| **Cloud Web Application Firewall (WAF)** | `PLANNED` | Rate limits and security headers are enforced at the Nginx layer; cloud edge WAF protection (Cloudflare, AWS WAF) is unconfigured. |
| **Database Encryption-at-Rest** | `DELEGATED` | Relies on Neon Cloud managed underlying AWS EBS volume encryption (AES-256). |
