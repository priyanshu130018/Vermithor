#!/usr/bin/env bash
# Vermithor Single Unified Demo Command
# Usage:
#   ./scripts/run-demo.sh [database | deployment | redis | memory | traffic | auth | ambiguous | all]

set -euo pipefail

SCENARIO="${1:-database}"
GATEWAY_URL="${VERMITHOR_API_URL:-http://localhost:8080}"

echo "=========================================================="
echo " Vermithor Interactive Demo Runner"
echo " Scenario: ${SCENARIO}"
echo "=========================================================="

python scripts/demo/synthetic-incidents/generator.py "${SCENARIO}" --api-url "${GATEWAY_URL}"
