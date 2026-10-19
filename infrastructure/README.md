# Vermithor — Kubernetes Deployment & Helm Orchestration

This directory contains the production-grade **Kubernetes manifests**, **Helm charts**, and **local cluster (`kind`) configurations** for the **Vermithor** AI Production Incident Intelligence Platform.

---

## 1. Architecture Overview

```text
                           Internet / Client Traffic
                                      │
                                      ▼ (Ingress: vermithor.local)
                 ┌────────────────────┴────────────────────┐
                 │                                         │
                 ▼ (/)                                     ▼ (/api/v1/*)
         Frontend Deployment                      API Gateway Deployment
          (Nginx SPA :80)                          (Nginx :80)
                                                           │
        ┌────────────┬──────────────┬──────────────┬───────┼──────────────┬────────────┐
        ▼            ▼              ▼              ▼       ▼              ▼            ▼
     Incident     Anomaly      Correlation        RCA   Log Intel      Retrieval     Summary
      :8002        :8003          :8004          :8005    :8006          :8007        :8008
        │            │              │              │       │              │            │
        └────────────┴──────────────┼──────────────┴───────┴──────────────┴────────────┘
                                    ▼
               ┌────────────────────┴────────────────────┐
               ▼                                         ▼
     PostgreSQL StatefulSet (:5432)             Redis Deployment (:6379)
     (PVC: 1Gi dev / 10Gi prod)
```

---

## 2. Helm Chart Structure

```text
deploy/helm/vermithor/
├── Chart.yaml                  # Chart metadata (v0.1.0)
├── values.yaml                 # Base configuration & resource limits
├── values-dev.yaml             # Lightweight local profile (1 replica, no HPA)
├── values-prod.yaml            # Production profile (multi-replicas, HPA, NetworkPolicies)
└── templates/
    ├── _helpers.tpl            # Label & naming helpers
    ├── namespace.yaml          # vermithor namespace
    ├── configmap.yaml          # Non-secret environment variables
    ├── secrets.yaml            # Sensitive credentials & JWT keys
    ├── gateway-deployment.yaml # Nginx API Gateway Deployment + Service
    ├── frontend-deployment.yaml# React SPA Deployment + Service
    ├── *-deployment.yaml       # All 8 backend microservices
    ├── postgres-statefulset.yaml# PostgreSQL with PVC
    ├── redis-deployment.yaml   # In-memory broker/caching
    ├── prometheus-deployment.yaml # Metrics scraper
    ├── grafana-deployment.yaml # Observability dashboards
    ├── jaeger-deployment.yaml  # Distributed tracing collector
    ├── ingress.yaml            # Host-based routing rules
    ├── hpa.yaml                # Autoscalers for stateless services
    ├── networkpolicies.yaml    # Traffic boundary policies
    └── db-migration-job.yaml   # Post-install Alembic DB migration Job
```

---

## 3. Local Development (`kind`)

### Step 1: Create local kind cluster
```bash
kind create cluster --config deploy/kind/cluster.yaml
```

### Step 2: Build & load images locally
```bash
docker build -t vermithor/gateway:0.1.0 ./gateway
docker build -t vermithor/frontend:0.1.0 ./frontend
docker build -t vermithor/ingestion-service:0.1.0 ./backend/services/ingestion-service
docker build -t vermithor/incident-service:0.1.0 ./backend/services/incident-service
docker build -t vermithor/anomaly-service:0.1.0 ./backend/services/anomaly-service
docker build -t vermithor/correlation-service:0.1.0 ./backend/services/correlation-service
docker build -t vermithor/rca-service:0.1.0 ./backend/services/rca-service
docker build -t vermithor/log-intelligence-service:0.1.0 ./backend/services/log-intelligence-service
docker build -t vermithor/retrieval-service:0.1.0 ./backend/services/retrieval-service
docker build -t vermithor/summary-service:0.1.0 ./backend/services/summary-service

kind load docker-image vermithor/gateway:0.1.0 --name vermithor-cluster
kind load docker-image vermithor/frontend:0.1.0 --name vermithor-cluster
kind load docker-image vermithor/ingestion-service:0.1.0 --name vermithor-cluster
kind load docker-image vermithor/incident-service:0.1.0 --name vermithor-cluster
kind load docker-image vermithor/anomaly-service:0.1.0 --name vermithor-cluster
kind load docker-image vermithor/correlation-service:0.1.0 --name vermithor-cluster
kind load docker-image vermithor/rca-service:0.1.0 --name vermithor-cluster
kind load docker-image vermithor/log-intelligence-service:0.1.0 --name vermithor-cluster
kind load docker-image vermithor/retrieval-service:0.1.0 --name vermithor-cluster
kind load docker-image vermithor/summary-service:0.1.0 --name vermithor-cluster
```

### Step 3: Install Helm Release (Dev Profile)
```bash
helm upgrade --install vermithor deploy/helm/vermithor \
  --namespace vermithor \
  --create-namespace \
  -f deploy/helm/vermithor/values-dev.yaml
```

---

## 4. Production Deployment

```bash
helm upgrade --install vermithor deploy/helm/vermithor \
  --namespace vermithor \
  --create-namespace \
  -f deploy/helm/vermithor/values-prod.yaml \
  --set jwt.secret="<STRONG_PRODUCTION_SECRET>" \
  --set database.password="<STRONG_DB_PASSWORD>"
```

### Rollback
```bash
helm rollback vermithor <REVISION_NUMBER> -n vermithor
```

---

## 5. Security & Isolation

- **Private Cluster DNS**: All internal services (`incident-service:8002`, `postgres:5432`, etc.) communicate exclusively over internal Kubernetes networking.
- **Ingress Boundary**: Only the React Frontend (`/`) and API Gateway (`/api/v1/*`, `/health`) are exposed externally through the Ingress controller.
- **Secrets Management**: Secrets are templated into `Secret` objects. In production, use external secret managers (Vault / AWS Secrets Manager / SealedSecrets).
