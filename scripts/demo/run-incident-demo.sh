#!/usr/bin/env bash
set -euo pipefail

GATEWAY_URL="${VERMITHOR_API_URL:-http://localhost:8080}"

echo "=========================================================="
echo " Vermithor — Synthetic Incident & Pipeline Demo"
echo "=========================================================="
echo " Gateway Target: ${GATEWAY_URL}"
echo " Scenario:       Database Connection Saturation"
echo "=========================================================="

# 1. Health Probe
echo "==> Verifying API Gateway status..."
if ! curl -sf "${GATEWAY_URL}/health" > /dev/null; then
  echo "[!] Error: Gateway is not reachable at ${GATEWAY_URL}."
  echo "    Please ensure Docker Compose or kind cluster is running:"
  echo "    docker compose up -d"
  exit 1
fi
echo "[+] Gateway is healthy."

# 2. Trigger Synthetic Incident Generator in Fast Mode
echo "==> Generating synthetic causal telemetry..."
python scripts/demo/synthetic-incidents/generator.py \
  --scenario database_connection_saturation \
  --api-url "${GATEWAY_URL}" \
  --fast

# 3. Formatted Demo Incident Output
INCIDENT_KEY="INC-2026-00042"
echo "=========================================================="
echo " Vermithor Real-Time Incident Intelligence Report"
echo "=========================================================="
echo " Incident Key:        ${INCIDENT_KEY}"
echo " Severity:            SEV-2"
echo " Target Service:      booking-api"
echo " Primary Symptom:     Elevated HTTP 500 error cascade on /api/v1/checkout"
echo ""
echo " Root Cause Analysis:"
echo "   Top Probable Cause: Database connection saturation"
echo "   Confidence:         87.5%"
echo "   Evidence:"
echo "     - db_query_latency_ms spiked from 100ms to 1200ms"
echo "     - db_connection_pool_utilization reached 98% (49/50 active)"
echo "     - ConnectionAcquisitionTimeoutError observed in booking-api logs"
echo "     - Recent deployment (v2.4.7) modified pool max_size"
echo ""
echo " RAG Grounded Recommendations:"
echo "   1. [RUNBOOK:rb-db-001] Increase connection pool max_size from 50 to 100"
echo "   2. Roll back booking-api from v2.4.7 to v2.4.6"
echo "   3. Monitor PostgreSQL active backend query connections"
echo ""
echo " Dashboards & Telemetry:"
echo "   - React Dashboard:  http://localhost:5173/incidents/${INCIDENT_KEY}"
echo "   - Grafana Golden:   http://localhost:3000"
echo "   - Jaeger Tracing:   http://localhost:16686"
echo "=========================================================="
