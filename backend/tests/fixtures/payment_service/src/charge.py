from src.config import DatabaseConfig


class PaymentPool:
    """Mock connection pool simulating HikariCP connection acquisition and release."""

    def __init__(self, config: DatabaseConfig):
        self.config = config
        self.active_connections = 0

    def acquire(self):
        if self.active_connections >= self.config.max_pool_size:
            raise TimeoutError(f"ConnectionAcquisitionTimeoutException: Pool '{self.config.pool_name}' exhausted")
        self.active_connections += 1
        return self

    def release(self):
        if self.active_connections > 0:
            self.active_connections -= 1

    def __enter__(self):
        return self.acquire()

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


def process_charge(pool: PaymentPool, amount: float, fail: bool = False) -> dict:
    """Execute charge transaction with guarded pool connection."""
    with pool:
        if fail:
            raise RuntimeError("Transaction processing failed unexpectedly")
        return {"status": "SUCCESS", "amount": amount}


def execute_payment_query(pool: PaymentPool, query_duration_ms: float) -> dict:
    """Execute database query with timeout guard to prevent connection hoarding from slow queries."""
    with pool:
        if query_duration_ms > pool.config.query_timeout_ms:
            raise TimeoutError(
                f"QueryExecutionTimeoutException: Query took {query_duration_ms}ms "
                f"(limit: {pool.config.query_timeout_ms}ms)"
            )
        return {"status": "SUCCESS", "duration_ms": query_duration_ms}
