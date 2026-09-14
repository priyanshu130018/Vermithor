import datetime
import os
import sys
import pytest

# Add tool directory to sys.path
tool_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if tool_dir not in sys.path:
    sys.path.insert(0, tool_dir)

from generator import (
    load_scenario,
    build_telemetry_batch,
    run_generator,
)
from client import VermithorClient, generate_dev_jwt


def test_load_scenario_valid():
    scenario = load_scenario("database_connection_saturation")
    assert scenario["name"] == "database_connection_saturation"
    assert scenario["target_service"] == "booking-api"
    assert len(scenario["timeline"]) >= 4


def test_load_scenario_nonexistent_raises():
    with pytest.raises(FileNotFoundError):
        load_scenario("non_existent_scenario_12345")


def test_build_telemetry_batch_structure():
    scenario = load_scenario("database_connection_saturation")
    scenario_id = "test-scenario-001"
    base_time = datetime.datetime.now(datetime.timezone.utc)

    batch = build_telemetry_batch(scenario, scenario_id, base_time)

    assert "events" in batch
    assert "observations" in batch
    assert "logs" in batch
    assert len(batch["events"]) > 0
    assert len(batch["observations"]) > 0
    assert len(batch["logs"]) > 0

    # Verify scenario ID propagation
    for obs in batch["observations"]:
        assert obs["metadata"]["scenario_id"] == scenario_id


def test_dry_run_generator():
    result = run_generator(
        scenario_name="database_connection_saturation",
        dry_run=True,
        scenario_id="dry-run-test-id",
    )
    assert result["status"] == "dry_run_success"
    assert result["scenario_id"] == "dry-run-test-id"
    assert result["counts"]["events"] > 0


def test_client_jwt_generation():
    token = generate_dev_jwt(subject="test-bot")
    parts = token.split(".")
    assert len(parts) == 3

    client = VermithorClient(base_url="http://localhost:8080")
    headers = client._headers(trace_id="4bf92f3577b34da6a3ce929d0e0e4736")
    assert "Authorization" in headers
    assert "traceparent" in headers
    assert headers["Authorization"].startswith("Bearer ")
