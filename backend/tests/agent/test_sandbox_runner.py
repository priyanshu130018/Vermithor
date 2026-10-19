import os
from pathlib import Path
import pytest

from backend.app.agent.runner.sandbox import IsolatedTestRunner, apply_unified_diff
from backend.app.agent.schemas.repair import ValidationStatus


def test_sanitize_env_strips_production_credentials(monkeypatch):
    """Verify that all production database URLs, JWT secrets, and API tokens are stripped."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://prod:secret@neon.tech/db")
    monkeypatch.setenv("JWT_SECRET", "super-secret-jwt-key")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_1234567890abcdef")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "sensitive-aws-key")
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))

    runner = IsolatedTestRunner()
    clean_env = runner.sanitize_env()

    assert "DATABASE_URL" not in clean_env
    assert "JWT_SECRET" not in clean_env
    assert "GITHUB_TOKEN" not in clean_env
    assert "AWS_SECRET_ACCESS_KEY" not in clean_env
    assert clean_env.get("VERMITHOR_ISOLATED_TEST") == "true"


def test_apply_unified_diff_modifies_target_file(tmp_path):
    """Verify that unified diff patches apply cleanly in isolated sandbox."""
    file_path = tmp_path / "config.py"
    file_path.write_text("pool_size = 10\ntimeout = 5000\n", encoding="utf-8")

    diff = """--- a/config.py
+++ b/config.py
@@ -1,2 +1,2 @@
-pool_size = 10
+pool_size = 50
 timeout = 5000
"""
    modified = apply_unified_diff(tmp_path, diff)
    assert modified == ["config.py"]
    updated_content = file_path.read_text(encoding="utf-8")
    assert "pool_size = 50" in updated_content
    assert "pool_size = 10" not in updated_content


def test_sandbox_blocks_command_injection(tmp_path):
    """Verify that command strings containing shell operators are blocked."""
    runner = IsolatedTestRunner()
    result = runner.run_validation(
        source_dir=tmp_path,
        test_command="pytest; rm -rf /",
    )
    assert result.status == ValidationStatus.VALIDATION_BLOCKED
    assert "disallowed shell operators" in result.error_message


def test_sandbox_blocks_unauthorized_binaries(tmp_path):
    """Verify that binaries not on the approved test runner whitelist are rejected."""
    runner = IsolatedTestRunner()
    result = runner.run_validation(
        source_dir=tmp_path,
        test_command="bash run_tests.sh",
    )
    assert result.status == ValidationStatus.VALIDATION_BLOCKED
    assert "not an authorized test runner" in result.error_message


def test_sandbox_enforces_execution_timeout(tmp_path):
    """Verify that tests exceeding timeout threshold are terminated safely."""
    test_file = tmp_path / "test_sleep.py"
    test_file.write_text("import time\ndef test_slow():\n    time.sleep(10)\n", encoding="utf-8")

    # Set aggressive 1-second timeout
    runner = IsolatedTestRunner(timeout_seconds=1.0)
    result = runner.run_validation(
        source_dir=tmp_path,
        test_command="pytest test_sleep.py",
    )
    assert result.status == ValidationStatus.VALIDATION_FAILED
    assert "timed out after 1.0 seconds" in (result.error_message or "")


def test_sandbox_clean_run_with_passing_and_failing_tests():
    """Verify running real tests against the payment_service fixture."""
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "payment_service"
    runner = IsolatedTestRunner(timeout_seconds=15.0)

    # 1. Unpatched run: fails because max_pool_size is 10 (assert >= 25 fails)
    unpatched_res = runner.run_validation(source_dir=fixture_dir, test_command="pytest tests/test_payment_pool.py")
    assert unpatched_res.status == ValidationStatus.VALIDATION_FAILED
    assert unpatched_res.failed >= 1

    # 2. Patched run: applies patch updating max_pool_size to 50
    patch = """--- a/src/config.py
+++ b/src/config.py
@@ -3,5 +3,5 @@
     pool_name: str = "PaymentPool"
     # Defect: max_pool_size reduced to 10 in deployment v2.8.4, causing rapid pool exhaustion
-    max_pool_size: int = 10
+    max_pool_size: int = 50
     connection_timeout: int = 5000
"""
    patched_res = runner.run_validation(
        source_dir=fixture_dir,
        patch_diff=patch,
        test_command="pytest tests/test_payment_pool.py",
    )
    assert patched_res.status == ValidationStatus.VALIDATED
    assert patched_res.passed == 4
    assert patched_res.failed == 0
