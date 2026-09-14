#!/usr/bin/env bash
set -euo pipefail

echo "=========================================================="
echo " Vermithor — Local Kubernetes (kind) Smoke Test"
echo "=========================================================="

CLUSTER_NAME="vermithor-cluster"

# 1. Create kind cluster if not exists
if ! kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
  echo "==> Creating kind cluster '${CLUSTER_NAME}'..."
  kind create cluster --config infrastructure/kubernetes/kind/cluster.yaml
else
  echo "==> kind cluster '${CLUSTER_NAME}' already active."
fi

# 2. Build local docker images
echo "==> Building container images..."
docker build -t vermithor/gateway:0.1.0 ./gateway
docker build -t vermithor/frontend:0.1.0 ./frontend
docker build -t vermithor/backend:0.1.0 ./backend
docker build -t vermithor/worker:0.1.0 ./backend

# 3. Load images into kind node
echo "==> Loading images into kind cluster..."
kind load docker-image vermithor/gateway:0.1.0 --name ${CLUSTER_NAME}
kind load docker-image vermithor/frontend:0.1.0 --name ${CLUSTER_NAME}
kind load docker-image vermithor/backend:0.1.0 --name ${CLUSTER_NAME}
kind load docker-image vermithor/worker:0.1.0 --name ${CLUSTER_NAME}

# 4. Install / Upgrade Helm Chart
echo "==> Deploying Vermithor Helm Chart with values-dev.yaml..."
helm upgrade --install vermithor infrastructure/helm/vermithor \
  --namespace vermithor \
  --create-namespace \
  -f infrastructure/helm/vermithor/values-dev.yaml

echo "==> Waiting for PostgreSQL StatefulSet..."
kubectl rollout status statefulset/postgres -n vermithor --timeout=60s

echo "==> Waiting for Gateway and Backend..."
kubectl rollout status deployment/vermithor-gateway -n vermithor --timeout=60s
kubectl rollout status deployment/vermithor-backend -n vermithor --timeout=60s

echo "==> Performing Gateway Health Probe..."
kubectl run curl-test --image=curlimages/curl:latest --rm -i --restart=Never -n vermithor -- curl -s http://vermithor-gateway/health

echo "=========================================================="
echo " Vermithor Smoke Test Succeeded! All services ready."
echo "=========================================================="
