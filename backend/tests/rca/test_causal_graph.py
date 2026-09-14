from backend.app.rca.analysis.causal_graph import CausalGraphBuilder


def test_causal_graph_construction():
    """Test directed graph creation and causal chain extraction."""
    signals = [
        {
            "signal_id": "dep-001",
            "signal_type": "DEPLOYMENT",
            "service": "booking-api",
            "timestamp": "2026-08-29T12:00:00Z",
        },
        {
            "signal_id": "anom-001",
            "signal_type": "ANOMALY",
            "service": "booking-api",
            "timestamp": "2026-08-29T12:01:30Z",
            "metadata": {"metric_name": "db_latency"},
        },
        {
            "signal_id": "err-001",
            "signal_type": "EVENT",
            "service": "booking-api",
            "timestamp": "2026-08-29T12:02:30Z",
            "metadata": {"event_type": "HTTP_500"},
        },
    ]

    edges, chain = CausalGraphBuilder.build_graph(signals)

    # Verify edges
    assert len(edges) == 3  # (dep->anom, dep->err, anom->err)
    dep_to_anom = next(e for e in edges if e["source_signal_id"] == "dep-001" and e["target_signal_id"] == "anom-001")
    assert dep_to_anom["relationship"] == "DEPLOYMENT_TRIGGER"

    anom_to_err = next(e for e in edges if e["source_signal_id"] == "anom-001" and e["target_signal_id"] == "err-001")
    assert anom_to_err["relationship"] == "METRIC_TO_ERROR"

    # Verify causal chain sequence
    assert len(chain) == 3
    assert chain[0]["signal_id"] == "dep-001"
    assert chain[0]["role"] == "possible_trigger"
    assert chain[1]["signal_id"] == "anom-001"
    assert chain[1]["role"] == "propagation_step"
    assert chain[2]["signal_id"] == "err-001"
    assert chain[2]["role"] == "downstream_effect"


def test_empty_signals_causal_graph():
    """Test empty signal input returns empty graph structures."""
    edges, chain = CausalGraphBuilder.build_graph([])
    assert edges == []
    assert chain == []
