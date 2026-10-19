class DatabaseConfig:
    """Database connection pool configuration for payment-api."""
    pool_name: str = "PaymentPool"
    # Defect: max_pool_size reduced to 10 in deployment v2.8.4, causing rapid pool exhaustion
    max_pool_size: int = 10
    connection_timeout: int = 5000
    idle_timeout: int = 600000
    query_timeout_ms: int = 1000
