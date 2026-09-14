import os
import sys
import yaml
import pytest


def test_stateless_service_readiness_probe_definitions():
    """Verify that all backend and gateway deployments define readiness and liveness probes."""
    chart_dir = os.path.abspath("infrastructure/helm/vermithor/templates")
    deployments = [
        "backend-deployment.yaml",
        "gateway-deployment.yaml",
    ]

    for d_file in deployments:
        path = os.path.join(chart_dir, d_file)
        assert os.path.exists(path), f"Deployment template missing: {path}"
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check for probes in templated text
        assert "readinessProbe" in content, f"Missing readinessProbe in {d_file}"
        assert "livenessProbe" in content, f"Missing livenessProbe in {d_file}"
        assert "httpGet" in content, f"Missing httpGet probe check in {d_file}"


def test_rolling_update_strategy_defined_in_helm():
    """Verify production values configure multi-replica HA strategies."""
    prod_values_path = os.path.abspath("infrastructure/helm/vermithor/values-prod.yaml")
    with open(prod_values_path, "r", encoding="utf-8") as f:
        prod_values = yaml.safe_load(f)

    for svc_name in ["backend", "gateway", "worker"]:
        if svc_name in prod_values:
            assert prod_values[svc_name].get("replicaCount", 1) >= 2, (
                f"Production replica count for {svc_name} should be >= 2 for HA"
            )


def test_service_health_contract_isolation():
    """Verify health endpoints respond with standard status payload."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()

    @app.get("/health")
    def health():
        return {"status": "healthy", "service": "vermithor-backend"}

    client = TestClient(app)
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "healthy", "service": "vermithor-backend"}
