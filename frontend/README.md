# Vermithor — SRE Incident Intelligence Dashboard (Frontend)

The **Vermithor Frontend** is a dark-first, high-information-density React application engineered for Site Reliability Engineers (SREs), DevOps teams, and incident commanders. It connects the 8 backend microservices (`:8001` through `:8008`) into an intuitive observability and incident response interface.

---

## Key Features

1. **Live Incident Command Center (`/`)**:
   - High-level metric cards for Active Incidents, Critical Outages, and Affected Services.
   - Microservice Health Matrix tracking availability across all 8 microservices.
   - Severity distribution telemetry charts.
   - Paginated active incident feed.
2. **Deep Incident Investigation (`/incidents/:incidentKey`)**:
   - **What Happened**: Incident Header, duration, severity, blast radius.
   - **When**: Visual chronological timeline with telemetry event citations (`[LOG:...]`, `[ANOMALY:...]`).
   - **Why**: Multi-signal correlation graph, directed causal chains, and ranked root cause candidates with confidence scores.
   - **Evidence**: Grounded evidence explorer with source tags, cosine similarity ratings, and content excerpts.
   - **What Next**: Similar historical incident matching, standard operational runbooks (SOPs), and AI recommended remediation.
   - **AI Summary**: Natural-language incident synthesis with real-time generation triggers and grounded RCA confidence notices.
3. **Log Intelligence & Vector Search (`/logs`)**:
   - Dense cosine vector search into `log-intelligence-service:8006` with template extraction tags and domain filters.
4. **Runbook Knowledge Base (`/runbooks`)**:
   - Searchable and categorized Standard Operating Procedures (SOPs) powered by `retrieval-service:8007`.

---

## Technology Stack

- **Framework**: React 18 + TypeScript + Vite
- **Routing**: React Router DOM v6
- **Server State & Caching**: TanStack Query v5 (`@tanstack/react-query`)
- **Styling**: Tailwind CSS (Dark theme tokens)
- **Data Visualization**: Recharts
- **Icons**: Lucide React
- **HTTP Client**: Axios
- **Testing**: Vitest + React Testing Library + jsdom

---

## Development Setup

```bash
# 1. Install dependencies
npm install

# 2. Start local development server (http://localhost:5173)
npm run dev

# 3. Run test suite
npm test

# 4. Build production bundle
npm run build
```

---

## Environment Configuration

Configure service URLs in `.env` (refer to `.env.example`):

```env
VITE_INCIDENT_SERVICE_URL=http://localhost:8002
VITE_ANOMALY_SERVICE_URL=http://localhost:8003
VITE_CORRELATION_SERVICE_URL=http://localhost:8004
VITE_RCA_SERVICE_URL=http://localhost:8005
VITE_LOG_INTELLIGENCE_URL=http://localhost:8006
VITE_RETRIEVAL_SERVICE_URL=http://localhost:8007
VITE_SUMMARY_SERVICE_URL=http://localhost:8008
```

---

## Docker Deployment

Build and run with Nginx:

```bash
docker build -t vermithor-frontend .
docker run -p 5173:80 vermithor-frontend
```
