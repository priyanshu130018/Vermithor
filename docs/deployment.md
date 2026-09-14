# Vermithor Deployment Guide

This guide covers deployment procedures for local Docker Compose and Kubernetes environments.

---

## 1. Local Development Deployment (Docker Compose)

### Prerequisites
- Docker Engine 24.0+ and Docker Compose v2.20+ (or Docker Desktop / WSL2).
- At least 4GB of available system RAM.
- Python 3.10+ (for local test runner execution).
- (Optional) Local Ollama instance if testing live LLM synthesis.

### Step-by-Step Startup

1. **Clone the repository and prepare environment configuration**:
   ```bash
   git clone <YOUR_GITHUB_REPOSITORY_URL>
   cd Vermithor
   cp .env.example .env
   ```

2. **Start the complete container stack**:
   ```bash
   docker compose up -d --build
   ```

3. **Verify running containers**:
   ```bash
   docker compose ps
   ```

4. **Access Platform UIs & APIs**:
   - **Frontend SRE Dashboard**: `http://localhost:5173`
   - **API Gateway**: `http://localhost:8080` (Health: `http://localhost:8080/health`)
   - **Grafana Monitoring**: `http://localhost:3000` (User: `admin`, Password: `admin_password`)
   - **Jaeger Tracing**: `http://localhost:16686`
   - **Prometheus Metrics**: `http://localhost:9090`

5. **Shutdown**:
   ```bash
   docker compose down
   ```

---

## 2. Kubernetes Deployment via Helm

### Prerequisites
- Kubernetes cluster v1.26+ (e.g. kind, Minikube, EKS, GKE, AKS).
- Helm v3.12+.
- `kubectl` configured with cluster administrator context.

### Step-by-Step Deployment

1. **Validate Helm Chart Syntax**:
   ```bash
   helm lint infrastructure/helm/vermithor
   ```

2. **Render and Inspect Manifests**:
   ```bash
   helm template vermithor infrastructure/helm/vermithor -f infrastructure/helm/vermithor/values-dev.yaml
   ```

3. **Deploy Helm Chart**:
   ```bash
   helm upgrade --install vermithor infrastructure/helm/vermithor \
     --namespace vermithor \
     --create-namespace \
     -f infrastructure/helm/vermithor/values-prod.yaml
   ```

4. **Verify Pod Rollout**:
   ```bash
   kubectl get pods -n vermithor
   kubectl get svc -n vermithor
   ```

5. **Port-Forward to Access Gateway & Dashboard**:
   ```bash
   kubectl port-forward svc/vermithor-gateway 8080:80 -n vermithor
   kubectl port-forward svc/vermithor-frontend 5173:80 -n vermithor
   ```
