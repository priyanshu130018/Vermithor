#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${K8S_NAMESPACE:-vermithor}"
TARGET_DEPLOYMENT="${1:-backend}"

echo "=========================================================="
echo " Vermithor — Kubernetes Resilience Smoke Test"
echo "=========================================================="
echo " Namespace:  ${NAMESPACE}"
echo " Target:     ${TARGET_DEPLOYMENT}"
echo "=========================================================="

# 1. Check kubectl connectivity
if ! kubectl get namespace "${NAMESPACE}" > /dev/null 2>&1; then
  echo "[!] Error: Namespace '${NAMESPACE}' not found or kubectl cannot connect to cluster."
  echo "    For local development, ensure kind cluster is active:"
  echo "    kind get clusters"
  exit 1
fi

# 2. Locate active pod
echo "==> Finding target pod for ${TARGET_DEPLOYMENT}..."
POD_NAME=$(kubectl get pods -n "${NAMESPACE}" -l "app.kubernetes.io/component=${TARGET_DEPLOYMENT}" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [[ -z "${POD_NAME}" ]]; then
  echo "[!] Error: No active pods found for deployment ${TARGET_DEPLOYMENT}"
  exit 1
fi

echo "[+] Target Pod: ${POD_NAME}"

# 3. Simulate failure by deleting pod
START_TIME=$(date +%s)
echo "==> Killing pod ${POD_NAME}..."
kubectl delete pod "${POD_NAME}" -n "${NAMESPACE}" --wait=false

# 4. Wait for replacement pod to be Running and Ready
echo "==> Waiting for Kubernetes to recreate and mark replacement pod Ready..."
kubectl wait --namespace="${NAMESPACE}" \
  --for=condition=ready pod \
  --selector="app.kubernetes.io/component=${TARGET_DEPLOYMENT}" \
  --timeout=60s

END_TIME=$(date +%s)
RECOVERY_TIME=$((END_TIME - START_TIME))

# 5. Get new pod name
NEW_POD_NAME=$(kubectl get pods -n "${NAMESPACE}" -l "app.kubernetes.io/component=${TARGET_DEPLOYMENT}" -o jsonpath='{.items[0].metadata.name}')

echo "=========================================================="
echo " Resilience Verification Succeeded!"
echo "=========================================================="
echo " Terminated Pod:   ${POD_NAME}"
echo " Replacement Pod:  ${NEW_POD_NAME}"
echo " Replacement Status: Ready"
echo " Measured Recovery Time: ${RECOVERY_TIME} seconds"
echo "=========================================================="
