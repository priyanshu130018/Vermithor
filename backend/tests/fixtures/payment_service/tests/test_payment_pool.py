import pytest
from src.config import DatabaseConfig
from src.charge import PaymentPool, execute_payment_query, process_charge


def test_pool_capacity_under_concurrency():
    """Verify that pool supports at least 25 concurrent connections for load handling."""
    config = DatabaseConfig()
    assert config.max_pool_size >= 25, (
        f"max_pool_size={config.max_pool_size} is dangerously low for production concurrency; must be >= 25"
    )


def test_charge_acquires_and_releases_connection():
    """Verify that normal transactions acquire and cleanly release connections."""
    config = DatabaseConfig()
    pool = PaymentPool(config)
    result = process_charge(pool, 49.99)
    assert result["status"] == "SUCCESS"
    assert pool.active_connections == 0


def test_connection_released_on_transaction_failure():
    """Verify that transaction exceptions do not leak connections."""
    config = DatabaseConfig()
    pool = PaymentPool(config)
    with pytest.raises(RuntimeError):
        process_charge(pool, 100.0, fail=True)
    assert pool.active_connections == 0, "Connection was leaked on transaction failure"


def test_query_timeout_prevents_connection_hoarding():
    """Verify that slow queries abort at query_timeout_ms and cleanly release the pool connection."""
    config = DatabaseConfig()
    pool = PaymentPool(config)
    with pytest.raises(TimeoutError):
        execute_payment_query(pool, query_duration_ms=2500.0)
    assert pool.active_connections == 0, "Connection remained acquired after query timeout"
