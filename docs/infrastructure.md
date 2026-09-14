# Vermithor Infrastructure & Deployment

Vermithor is designed for dual deployment models: local rapid development via **Docker Compose** and container orchestrator deployment via **Kubernetes & Helm**.

---

## 1. Local Development Architecture (Docker Compose)

The local development environment is orchestrated via the root `docker-compose.yml`:

```bash
# Start the full 15-container stack
docker compose up -d --build

# Check container status
docker compose ps
```

### Compose Container Stack

| Service Name | Container Name | Port Mappings | Image / Context |
|---|---|---|---|
| `gateway` | `vermithor-gateway` | `8080:80` | `./gateway/Dockerfile` (OpenResty) |
| `postgres` | `vermithor-postgres` | `5432:5432` | `pgvector/pgvector:pg16` |
| `redis` | `vermithor-redis` | `6379:6379` | `redis:7-alpine` |
| `jaeger` | `vermithor-jaeger` | `16686:16686`, `4318:4318` | `jaegertracing/all-in-one:latest` |
| `prometheus`| `vermithor-prometheus` | `9090:9090` | `prom/prometheus:latest` |
| `grafana` | `vermithor-grafana` | `3000:3000` | `grafana/grafana:latest` |
| `ingestion-service` | `vermithor-ingestion-service` | Internal | `./backend/services/ingestion` |
| `worker` | `vermithor-celery-worker` | Internal | `./backend/services/ingestion` |
| `incident-service` | `vermithor-incident-service` | Internal | `./backend/services/incident` |
| `anomaly-service` | `vermithor-anomaly-service` | Internal | `./backend/services/anomaly` |
| `correlation-service`| `vermithor-correlation-service`| Internal | `./backend/services/correlation` |
| `rca-service` | `vermithor-rca-service` | Internal | `./backend/services/rca` |
| `log-intelligence-service`| `vermithor-log-intelligence-service`| Internal | `./backend/services/log-intelligence` |
| `retrieval-service`| `vermithor-retrieval-service` | Internal | `./backend/services/retrieval` |
| `summary-service` | `vermithor-summary-service` | Internal | `./backend/services/summary` |
| `frontend` | `vermithor-frontend` | `5173:80` | `./frontend/Dockerfile` (Nginx SPA) |

---

## 2. Kubernetes & Helm Deployment

Production-grade deployment manifests are maintained under `infrastructure/helm/vermithor/`:

```text
infrastructure/
├── helm/
│   └── vermithor/
│       ├── Chart.yaml         # Helm v2 chart definition (v0.1.0)
│       ├── values.yaml        # Default base configuration
│       ├── values-dev.yaml    # Resource-constrained dev cluster overrides
│       ├── values-prod.yaml   # Production HA overrides with HPA & replica counts
│       └── templates/         # Kubernetes resource manifests
│           ├── namespace.yaml
│           ├── secrets.yaml
│           ├── configmap.yaml
│           ├── networkpolicies.yaml
│           ├── ingress.yaml
│           ├── postgres-statefulset.yaml
│           ├── redis-deployment.yaml
│           ├── gateway-deployment.yaml
│           ├── frontend-deployment.yaml
│           ├── *-deployment.yaml (All 8 microservices)
│           ├── hpa.yaml
│           └── db-migration-job.yaml
└── kubernetes/
    └── kind/
        └── cluster.yaml       # Multi-node local kind cluster specification
```

### Helm Deployment Commands

```bash
# Validate chart syntax
helm lint infrastructure/helm/vermithor

# Render templates with development values
helm template vermithor infrastructure/helm/vermithor -f infrastructure/helm/vermithor/values-dev.yaml

# Deploy to active Kubernetes cluster
helm upgrade --install vermithor infrastructure/helm/vermithor \
  --namespace vermithor \
  --create-namespace \
  -f infrastructure/helm/vermithor/values-prod.yaml
```

---

## 3. Kubernetes Network Isolation & Security Policies

- **Default Deny Policy**: East-West traffic between pods is restricted by `NetworkPolicies`.
- **Gateway Ingress**: Only the `gateway` pod is permitted to receive external ingress traffic.
- **Backend Isolation**: Microservices can only receive incoming traffic from the `gateway` pod and dispatch database queries to the `postgres` StatefulSet.
- **Non-Root Containers**: All microservice containers define `securityContext` restricting execution to non-root user IDs.
