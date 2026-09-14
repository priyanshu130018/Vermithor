# Vermithor Frontend Architecture

The Vermithor dashboard is a Single Page Application (SPA) built with React 18, TypeScript, Vite, Tailwind CSS, and TanStack React Query.

---

## 1. Directory Structure

```text
frontend/
├── src/
│   ├── api/                   # Typed REST API clients communicating via Gateway (:8080)
│   │   ├── client.ts          # Central Axios/Fetch wrapper with JWT attachment
│   │   ├── incidents.ts       # Incident list, detail, & status update APIs
│   │   ├── rca.ts             # Causal graph DAG & candidate ranking APIs
│   │   ├── retrieval.ts       # RAG context & runbook APIs
│   │   ├── summaries.ts       # AI summary generation & polling APIs
│   │   ├── logs.ts            # Semantic log search APIs
│   │   └── anomalies.ts       # Metric anomaly observation APIs
│   │
│   ├── auth/                  # Client-side JWT generation and mock auth for local SRE demo
│   │   ├── auth.ts
│   │   └── token.ts
│   │
│   ├── components/            # Reusable UI component library
│   │   ├── common/            # Badges, Cards, ConfidenceBars, Loading & Error states
│   │   ├── dashboard/         # Global Incident Stats, Severity distribution chart, Service health
│   │   ├── incident/          # Incident Header, Causal Graph DAG, Evidence Table, AI Summary card, Runbooks
│   │   ├── layout/            # AppShell, Topbar, Sidebar navigation, Breadcrumbs
│   │   └── logs/              # Log stream viewer, filter bar, semantic search input
│   │
│   ├── hooks/                 # TanStack Query custom hooks for data fetching & caching
│   ├── pages/                 # Route views (Dashboard, Incidents, IncidentDetails, Logs, Runbooks)
│   ├── types/                 # TypeScript data contracts matching backend Pydantic schemas
│   └── styles/                # Tailwind CSS design system
│
├── index.html                 # Single page application HTML entrypoint
├── vite.config.ts             # Vite build & Vitest test runner configuration
├── nginx.conf                 # Production Nginx container reverse proxy configuration
└── Dockerfile                 # Multi-stage production container build (Node -> Nginx)
```

---

## 2. Gateway Communication Boundary

The frontend **never communicates directly with individual microservice ports**. All outbound requests target the API Gateway:

```text
React SPA (Port 5173 / Nginx) ──► HTTP Requests ──► API Gateway (Port 8080)
                                                    │
                                                    ├──► /api/v1/incidents -> :8002
                                                    ├──► /api/v1/rca       -> :8005
                                                    ├──► /api/v1/summaries -> :8008
                                                    └──► /api/v1/logs      -> :8006
```

### Environment Configuration
- The frontend uses a single public environment variable:
  `VITE_API_BASE_URL=http://localhost:8080`
- **Security Rule**: No database passwords, server private keys, or backend secrets are ever placed in frontend `.env` files.

---

## 3. Key Views & Capabilities

1. **SRE Incident Dashboard (`/`)**:
   - Live MTTR, Active Incidents by Severity (CRITICAL, HIGH, MEDIUM, LOW), Service Health status grid.
2. **Incident Details & Causal Graph Explorer (`/incidents/:key`)**:
   - **Interactive Causal DAG**: Visualizes the propagation path from root cause to affected downstream services.
   - **Grounded AI Synthesis**: Executive summary, what happened, probable root cause, and verified citation evidence.
   - **Operational Runbook Drawer**: Matched mitigation playbooks with step-by-step resolution commands.
3. **Log Intelligence & Semantic Search (`/logs`)**:
   - Real-time log table with domain tags and pgvector-backed semantic similarity queries.
4. **Runbook Knowledge Base (`/runbooks`)**:
   - Searchable library of operational procedures and troubleshooting guides.
