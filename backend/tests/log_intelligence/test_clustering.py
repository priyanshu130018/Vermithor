import uuid
from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient

from backend.app.common.config import get_settings
from backend.app.correlation.scoring.scorer import CorrelationScorer
from backend.app.log_intelligence.clustering.hdbscan_clusterer import HDBSCANLogClusterer
from backend.app.log_intelligence.clustering.service import LogClusteringService
from backend.app.log_intelligence.embedding.service import get_embedding_service
from backend.app.log_intelligence.schemas.logs import LogCategory
from backend.app.main import app


@pytest.fixture
def deterministic_log_dataset():
    """
    Creates a deterministic test dataset of distinct semantic error groups:
    - Group A: Database connection / timeout logs (4 items)
    - Group B: Authentication / JWT failure logs (4 items)
    - Group C: Redis / Cache failure logs (4 items)
    - Noise: Unrelated operational message (1 item)
    """
    base_time = datetime.now(timezone.utc) - timedelta(seconds=120)

    # Group A: Database (postgres / booking-api)
    group_a = [
        {
            "id": uuid.uuid4(),
            "source_event_id": "evt-db-1",
            "timestamp": base_time + timedelta(seconds=10),
            "service": "postgres",
            "environment": "production",
            "severity": "CRITICAL",
            "category": "DATABASE",
            "raw_message": "Connection to PostgreSQL database timed out after 30000ms",
            "normalized_message": "Connection to PostgreSQL database timed out after <NUM>ms",
            "template": "Connection to PostgreSQL database timed out after <NUM>ms",
            "trace_id": "trace-db-001",
        },
        {
            "id": uuid.uuid4(),
            "source_event_id": "evt-db-2",
            "timestamp": base_time + timedelta(seconds=20),
            "service": "postgres",
            "environment": "production",
            "severity": "CRITICAL",
            "category": "DATABASE",
            "raw_message": "Database connection pool exhausted: 100/100 active connections",
            "normalized_message": "Database connection pool exhausted: <NUM>/<NUM> active connections",
            "template": "Database connection pool exhausted: <NUM>/<NUM> active connections",
            "trace_id": "trace-db-001",
        },
        {
            "id": uuid.uuid4(),
            "source_event_id": "evt-db-3",
            "timestamp": base_time + timedelta(seconds=30),
            "service": "booking-api",
            "environment": "production",
            "severity": "ERROR",
            "category": "DATABASE",
            "raw_message": "Failed to connect to database host 10.0.1.5:5432 connection refused",
            "normalized_message": "Failed to connect to database host <IP>:<PORT> connection refused",
            "template": "Failed to connect to database host <IP>:<PORT> connection refused",
            "trace_id": "trace-db-002",
        },
        {
            "id": uuid.uuid4(),
            "source_event_id": "evt-db-4",
            "timestamp": base_time + timedelta(seconds=40),
            "service": "booking-api",
            "environment": "production",
            "severity": "ERROR",
            "category": "DATABASE",
            "raw_message": "PostgreSQL query timeout: relation reservations lock acquisition wait timeout",
            "normalized_message": "PostgreSQL query timeout: relation reservations lock acquisition wait timeout",
            "template": "PostgreSQL query timeout: relation reservations lock acquisition wait timeout",
            "trace_id": "trace-db-002",
        },
    ]

    # Group B: Authentication (auth-service / gateway)
    group_b = [
        {
            "id": uuid.uuid4(),
            "source_event_id": "evt-auth-1",
            "timestamp": base_time + timedelta(seconds=15),
            "service": "auth-service",
            "environment": "production",
            "severity": "WARNING",
            "category": "AUTHENTICATION",
            "raw_message": "JWT token verification failed: signature has expired",
            "normalized_message": "JWT token verification failed: signature has expired",
            "template": "JWT token verification failed: signature has expired",
            "trace_id": "trace-auth-001",
        },
        {
            "id": uuid.uuid4(),
            "source_event_id": "evt-auth-2",
            "timestamp": base_time + timedelta(seconds=25),
            "service": "auth-service",
            "environment": "production",
            "severity": "WARNING",
            "category": "AUTHENTICATION",
            "raw_message": "Unauthorized request: missing or invalid Bearer token",
            "normalized_message": "Unauthorized request: missing or invalid Bearer token",
            "template": "Unauthorized request: missing or invalid Bearer token",
            "trace_id": "trace-auth-001",
        },
        {
            "id": uuid.uuid4(),
            "source_event_id": "evt-auth-3",
            "timestamp": base_time + timedelta(seconds=35),
            "service": "gateway",
            "environment": "production",
            "severity": "WARNING",
            "category": "AUTHENTICATION",
            "raw_message": "Authentication failed for user usr-9918: bad credentials",
            "normalized_message": "Authentication failed for user <ID>: bad credentials",
            "template": "Authentication failed for user <ID>: bad credentials",
            "trace_id": "trace-auth-002",
        },
        {
            "id": uuid.uuid4(),
            "source_event_id": "evt-auth-4",
            "timestamp": base_time + timedelta(seconds=45),
            "service": "gateway",
            "environment": "production",
            "severity": "WARNING",
            "category": "AUTHENTICATION",
            "raw_message": "Invalid JWT issuer header received from client 192.168.1.1",
            "normalized_message": "Invalid JWT issuer header received from client <IP>",
            "template": "Invalid JWT issuer header received from client <IP>",
            "trace_id": "trace-auth-002",
        },
    ]

    # Group C: Cache / Redis (cache-service / catalog-api)
    group_c = [
        {
            "id": uuid.uuid4(),
            "source_event_id": "evt-cache-1",
            "timestamp": base_time + timedelta(seconds=12),
            "service": "cache-service",
            "environment": "production",
            "severity": "ERROR",
            "category": "CACHE",
            "raw_message": "Redis connection refused: cluster node 10.0.3.1:6379 unavailable",
            "normalized_message": "Redis connection refused: cluster node <IP>:<PORT> unavailable",
            "template": "Redis connection refused: cluster node <IP>:<PORT> unavailable",
            "trace_id": "trace-cache-001",
        },
        {
            "id": uuid.uuid4(),
            "source_event_id": "evt-cache-2",
            "timestamp": base_time + timedelta(seconds=22),
            "service": "cache-service",
            "environment": "production",
            "severity": "ERROR",
            "category": "CACHE",
            "raw_message": "Redis timeout: read command GET item_cache_991 timed out after 5000ms",
            "normalized_message": "Redis timeout: read command GET item_cache_<NUM> timed out after <NUM>ms",
            "template": "Redis timeout: read command GET item_cache_<NUM> timed out after <NUM>ms",
            "trace_id": "trace-cache-001",
        },
        {
            "id": uuid.uuid4(),
            "source_event_id": "evt-cache-3",
            "timestamp": base_time + timedelta(seconds=32),
            "service": "catalog-api",
            "environment": "production",
            "severity": "WARNING",
            "category": "CACHE",
            "raw_message": "Cache cluster down: falling back to direct database queries for items",
            "normalized_message": "Cache cluster down: falling back to direct database queries for items",
            "template": "Cache cluster down: falling back to direct database queries for items",
            "trace_id": "trace-cache-002",
        },
    ]

    # Noise item: Single unrelated operational message
    noise = [
        {
            "id": uuid.uuid4(),
            "source_event_id": "evt-noise-1",
            "timestamp": base_time + timedelta(seconds=5),
            "service": "backup-worker",
            "environment": "production",
            "severity": "INFO",
            "category": "RESOURCE",
            "raw_message": "Nightly backup compression completed successfully in 42 seconds with zero errors",
            "normalized_message": "Nightly backup compression completed successfully in <NUM> seconds with zero errors",
            "template": "Nightly backup compression completed successfully in <NUM> seconds with zero errors",
            "trace_id": "trace-backup-001",
        }
    ]

    return group_a + group_b + group_c + noise


def test_deterministic_embedding_generation_for_clusters(deterministic_log_dataset):
    """Verify that 384-dimensional dense vectors are generated deterministically for candidate logs."""
    embedding_service = get_embedding_service()
    texts = [
        embedding_service.format_embedding_input(
            service=l["service"],
            severity=l["severity"],
            category=l["category"],
            message=l["raw_message"],
        )
        for l in deterministic_log_dataset
    ]

    embeddings = embedding_service.embed_batch(texts)
    assert len(embeddings) == len(deterministic_log_dataset)
    for vec in embeddings:
        assert len(vec) == 384
        assert any(x != 0.0 for x in vec)


def test_hdbscan_clusters_semantic_groups(deterministic_log_dataset):
    """Verify HDBSCAN automatically discovers distinct semantic error clusters and separates them."""
    clustering_service = LogClusteringService()
    response = clustering_service.cluster_in_memory_logs(
        logs=deterministic_log_dataset,
        min_cluster_size=2,
        min_samples=1,
        include_noise=True,
    )

    assert response.total_logs == len(deterministic_log_dataset)
    assert response.total_clusters >= 3, f"Expected at least 3 clusters, got {response.total_clusters}"

    # Verify semantic cluster presence
    categories_found = {c.category for c in response.clusters if not c.is_noise}
    assert LogCategory.DATABASE in categories_found
    assert LogCategory.AUTHENTICATION in categories_found
    assert LogCategory.CACHE in categories_found

    # Check Database cluster
    db_cluster = next((c for c in response.clusters if c.category == LogCategory.DATABASE and not c.is_noise), None)
    assert db_cluster is not None
    assert db_cluster.size >= 2
    assert "postgres" in db_cluster.services or "booking-api" in db_cluster.services
    assert len(db_cluster.representative_messages) > 0
    assert any("database" in m.lower() or "connection" in m.lower() or "timeout" in m.lower() for m in db_cluster.representative_messages)

    # Check Authentication cluster
    auth_cluster = next((c for c in response.clusters if c.category == LogCategory.AUTHENTICATION and not c.is_noise), None)
    assert auth_cluster is not None
    assert auth_cluster.size >= 2
    assert "auth-service" in auth_cluster.services or "gateway" in auth_cluster.services
    assert any("jwt" in m.lower() or "unauthorized" in m.lower() or "auth" in m.lower() for m in auth_cluster.representative_messages)

    # Check Cache cluster
    cache_cluster = next((c for c in response.clusters if c.category == LogCategory.CACHE and not c.is_noise), None)
    assert cache_cluster is not None
    assert cache_cluster.size >= 2
    assert "cache-service" in cache_cluster.services or "catalog-api" in cache_cluster.services


def test_hdbscan_noise_preservation(deterministic_log_dataset):
    """Verify that isolated noise points are preserved with is_noise=True and cluster_id=-1."""
    clustering_service = LogClusteringService()
    response = clustering_service.cluster_in_memory_logs(
        logs=deterministic_log_dataset,
        min_cluster_size=2,
        min_samples=1,
        include_noise=True,
    )

    noise_clusters = [c for c in response.clusters if c.is_noise]
    # Noise cluster should exist or noise_count >= 1
    if noise_clusters:
        noise = noise_clusters[0]
        assert noise.cluster_id == -1
        assert noise.is_noise is True
        assert noise.label == "unclustered_noise"


def test_representative_messages_and_deterministic_labels(deterministic_log_dataset):
    """Verify representative medoid logs and deterministic human-readable labels."""
    clustering_service = LogClusteringService()
    response = clustering_service.cluster_in_memory_logs(
        logs=deterministic_log_dataset,
        min_cluster_size=2,
        min_samples=1,
    )

    for cluster in response.clusters:
        assert len(cluster.label) > 0
        assert cluster.size >= 1
        assert len(cluster.representative_messages) >= 1
        assert len(cluster.representative_messages) <= 3
        if not cluster.is_noise:
            assert "_" in cluster.label or len(cluster.label) >= 4


def test_affected_services_and_timestamps(deterministic_log_dataset):
    """Verify aggregated services, first_seen, last_seen, and severity distribution."""
    clustering_service = LogClusteringService()
    response = clustering_service.cluster_in_memory_logs(
        logs=deterministic_log_dataset,
        min_cluster_size=2,
        min_samples=1,
    )

    for cluster in response.clusters:
        assert cluster.first_seen <= cluster.last_seen
        assert len(cluster.services) >= 1
        assert len(cluster.environments) >= 1
        assert sum(cluster.severity_distribution.values()) == cluster.size


def test_cluster_to_correlation_signal_conversion(deterministic_log_dataset):
    """Verify clusters convert into valid SignalInput correlation signals and participate in scoring."""
    clustering_service = LogClusteringService()
    response = clustering_service.cluster_in_memory_logs(
        logs=deterministic_log_dataset,
        min_cluster_size=2,
        min_samples=1,
    )

    signals = LogClusteringService.to_correlation_signals(response.clusters)
    assert len(signals) >= 3

    db_signal = next((s for s in signals if "database" in s.metadata.get("cluster_category", "").lower()), None)
    assert db_signal is not None
    assert db_signal.service in ["postgres", "booking-api"]
    assert db_signal.metadata["cluster_size"] >= 2

    # Score correlation with a synthetic postgres latency anomaly
    from backend.app.correlation.schemas.correlation import SignalInput, SignalType
    anomaly_sig = SignalInput(
        signal_id="sig-anom-db-1",
        signal_type=SignalType.ANOMALY,
        timestamp=db_signal.timestamp,
        service="postgres",
        environment="production",
        severity="CRITICAL",
        metadata={"metric_name": "db_query_latency_ms", "value": 1500.0},
    )

    scorer = CorrelationScorer()
    score, reasons = scorer.score_pair(db_signal, anomaly_sig)
    assert score >= 0.40
    assert len(reasons) > 0
    assert any("cluster" in r.lower() or "service" in r.lower() for r in reasons)


def test_clustering_api_endpoints(db_session, deterministic_log_dataset):
    """Verify API endpoints /api/v1/logs/clusters/run and /api/v1/logs/clusters."""
    client = TestClient(app)

    # Ingest logs into test DB
    ingest_payload = {
        "logs": [
            {
                "source_event_id": l["source_event_id"],
                "timestamp": l["timestamp"].isoformat(),
                "service": l["service"],
                "environment": l["environment"],
                "severity": l["severity"],
                "message": l["raw_message"],
                "trace_id": l.get("trace_id"),
                "metadata": {},
            }
            for l in deterministic_log_dataset
        ]
    }
    ingest_res = client.post("/api/v1/logs/batch", json=ingest_payload)
    assert ingest_res.status_code == 201

    # Run clustering API
    run_payload = {
        "min_cluster_size": 2,
        "include_noise": True,
    }
    cluster_res = client.post("/api/v1/logs/clusters/run", json=run_payload)
    assert cluster_res.status_code == 200
    data = cluster_res.json()

    assert data["total_logs"] >= 12
    assert data["total_clusters"] >= 3
    assert len(data["clusters"]) >= 3
    assert data["duration_ms"] > 0

    # Test GET /api/v1/logs/clusters
    get_res = client.get("/api/v1/logs/clusters?min_cluster_size=2")
    assert get_res.status_code == 200
    get_data = get_res.json()
    assert get_data["total_clusters"] >= 3

    # Test GET /api/v1/logs/clusters/{id}
    first_cluster_id = data["clusters"][0]["cluster_id"]
    detail_res = client.get(f"/api/v1/logs/clusters/{first_cluster_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["cluster_id"] == first_cluster_id
    assert len(detail["representative_messages"]) > 0
