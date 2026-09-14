# Vermithor — Production API Gateway & Security Boundary

The **API Gateway** is the single entry point and security boundary for the **Vermithor** AI Production Incident Intelligence Platform, running on port `8080`. It isolates internal backend microservices from direct public exposure and enforces cryptographic JWT validation, tiered rate limiting, CORS policies, security headers, request ID propagation, and timeout budgets.

---

## Architectural Trust Boundary

```text
                    UNTRUSTED
                       │
                       ▼
                    Internet / Browser (:5173)
                       │
                       ▼
                ┌──────────────┐
                │ API Gateway  │ (:8080)
                │              │
                │ JWT Auth     │
                │ Rate Limits  │
                │ CORS Policy  │
                │ Headers      │
                └──────┬───────┘
                       │
                       ▼
                    TRUSTED (vermithor-network)
                       │
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
     Incident      Retrieval      Summary
       :8002         :8007         :8008
```

---

## Routing Table

| Public Path Pattern | Upstream Microservice | Rate Limit | Timeout | Auth Required |
| :--- | :--- | :--- | :--- | :--- |
| `GET /health` | Gateway Liveness | None | 5s | **No** (Public) |
| `/api/v1/incidents/*` | `incident-service:8002` | 30 req/s | 15s | **Yes** (JWT) |
| `/api/v1/observations/*` | `anomaly-service:8003` | 30 req/s | 15s | **Yes** (JWT) |
| `/api/v1/correlations/*` | `correlation-service:8004` | 30 req/s | 15s | **Yes** (JWT) |
| `/api/v1/rca/*` | `rca-service:8005` | 30 req/s | 15s | **Yes** (JWT) |
| `/api/v1/logs/*` | `log-intelligence-service:8006`| 10 req/s | 15s | **Yes** (JWT) |
| `/api/v1/retrieval/*` | `retrieval-service:8007` | 30 req/s | 15s | **Yes** (JWT) |
| `/api/v1/rag/*` | `retrieval-service:8007` | 30 req/s | 15s | **Yes** (JWT) |
| `/api/v1/runbooks/*` | `retrieval-service:8007` | 30 req/s | 15s | **Yes** (JWT) |
| `/api/v1/summaries/*` | `summary-service:8008` | 2 req/s | 130s | **Yes** (JWT) |
| `/api/v1/events/*` | `ingestion-service:8001` | 30 req/s | 15s | **Yes** (JWT) |

---

## Security & Access Control

1. **JWT Bearer Authentication**:
   - Header: `Authorization: Bearer <token>`
   - Validation: HMAC-SHA256 signature against `JWT_SECRET`, issuer (`iss: "vermithor"`), audience (`aud: "vermithor-api"`), and expiration (`exp > now()`).
   - Unauthenticated requests receive structured JSON `401 Unauthorized`.
2. **Tiered Rate Limiting**:
   - `api_general`: 30 requests/second (burst 20) for standard telemetry.
   - `api_summary`: 2 requests/second (burst 5) protecting compute-heavy LLM synthesis.
   - `api_logs`: 10 requests/second (burst 10) for dense vector search queries.
3. **Security Headers**:
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`
   - `Referrer-Policy: strict-origin-when-cross-origin`
   - `Content-Security-Policy`: Strict script/font/connect restrictions.
4. **Request Tracing**:
   - `X-Request-ID` is preserved from inbound headers or auto-generated and propagated to all upstream services and response headers.
5. **CORS**:
   - Origin-validated for configured frontend origins (`http://localhost:5173`). Preflight `OPTIONS` requests return `204 No Content`.
6. **Payload Size**:
   - Max body size capped at `10m`.

---

## Development vs Production Configuration

- **Development**:
  - `JWT_SECRET=vermithor-dev-secret-key-32-chars-min`
  - Frontend automatically provides client development tokens.
- **Production**:
  - `JWT_SECRET` injected securely via secret management / environment variables.
  - Internal microservices, PostgreSQL, and Redis communicate exclusively via `vermithor-network` without exposing host ports.
  - HTTPS / TLS termination configured at gateway.
