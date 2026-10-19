# Vermithor — API Gateway & Reverse Proxy

The **API Gateway** is the single entry point and perimeter boundary for the **Vermithor** AI Production Incident Intelligence Platform, running on port `8080`. Built on standard **Nginx (`nginx:alpine`)**, it reverse-proxies requests to the FastAPI backend, enforces tiered rate limiting, applies hardened HTTP security headers, propagates request IDs, and configures upstream timeouts without requiring Lua or OpenResty runtime dependencies.

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
                │ Nginx Gateway│ (:8080)
                │              │
                │ Rate Limits  │
                │ Proxy Pass   │
                │ Headers      │
                │ Request-ID   │
                └──────┬───────┘
                       │ (Authorization: Bearer <token>)
                       ▼
                    TRUSTED (vermithor-network)
                       │
                       ▼
          ┌───────────────────────────┐
          │  FastAPI Modular Monolith │ (:8000)
          │  - JWT Auth Enforcement   │
          │  - Domain Module Routers  │
          │  - Hugging Face RAG LLM   │
          └───────────────────────────┘
```

---

## Routing Table

| Public Path Pattern | Target Upstream | Rate Limit | Timeout | Auth Required |
| :--- | :--- | :--- | :--- | :--- |
| `GET /health` | Gateway Liveness | None | 5s | **No** (Public) |
| `GET /ready` | Backend Readiness | 30 req/s | 15s | **No** (Public) |
| `/api/v1/summaries/*` | `vermithor-backend:8000` | 2 req/s | 130s | **Yes** (FastAPI JWT) |
| `/api/v1/logs/*` | `vermithor-backend:8000` | 10 req/s | 15s | **Yes** (FastAPI JWT) |
| `/api/v1/*` | `vermithor-backend:8000` | 30 req/s | 15s | **Yes** (FastAPI JWT) |
| `/` (Docs / Root) | `vermithor-backend:8000` | None | 15s | **No** (Public) |

---

## Security & Access Control

1. **FastAPI JWT Authentication**:
   - Header: `Authorization: Bearer <token>`
   - Validation: Native Python/FastAPI verification via `backend/app/common/security.py`.
   - Validates cryptographic HS256 signature, required claims (`sub`, `exp`, `iss`, `aud`), expiration, and 30s clock skew tolerance.
   - Unauthenticated or invalid requests receive structured JSON `401 Unauthorized`.
2. **Tiered Rate Limiting**:
   - `api_general`: 30 requests/second (burst 20) for standard telemetry.
   - `api_summary`: 2 requests/second (burst 5, timeout 130s) protecting compute-heavy LLM synthesis.
   - `api_logs`: 10 requests/second (burst 20) for log search and ingestion.
3. **Security Headers**:
   - `X-Content-Type-Options: nosniff`
   - `X-Frame-Options: DENY`
   - `Referrer-Policy: strict-origin-when-cross-origin`
   - `Content-Security-Policy`: Strict script/font/connect restrictions.
4. **Request Tracing**:
   - `X-Request-ID` is preserved from inbound headers or generated as `$request_id` and forwarded upstream.
5. **Payload Size**:
   - Max body size capped at `10m`.

---

## Configuration & Local Testing

- **Docker Base Image**: `nginx:alpine` (standard Nginx, zero Lua/LuaRocks dependencies).
- **Backend JWT Settings**: Handled centrally via `backend/app/common/config.py` (`JWT_SECRET`, `JWT_ISSUER`, `JWT_AUDIENCE`).
- **Gateway Compose Config**: No redundant `JWT_*` environment variables required on the gateway container.
