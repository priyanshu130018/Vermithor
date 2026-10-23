import pytest
from fastapi import HTTPException
from unittest.mock import MagicMock, patch

from backend.app.common.security import (
    verify_org_access,
    get_effective_allowed_orgs,
    is_org_authorized,
    DEFAULT_ALLOWED_ORGS,
)
from backend.app.common.config import Settings


def test_missing_org_claim_fails_closed():
    """Verify that an authentication payload lacking org_id/organization/org raises HTTP 403."""
    with pytest.raises(HTTPException) as exc_info:
        verify_org_access({})
    assert exc_info.value.status_code == 403
    assert "Missing required organization claim" in exc_info.value.detail

    with pytest.raises(HTTPException) as exc_info:
        verify_org_access({"org_id": "   "})
    assert exc_info.value.status_code == 403
    assert "Missing required organization claim" in exc_info.value.detail


def test_malformed_org_claim_fails_closed():
    """Verify that org identifiers with special characters, injections, or traversal attempts raise HTTP 403."""
    malformed_orgs = [
        "org/../admin",
        "org$attacker",
        "org;DROP TABLE users;",
        "org alpha",
        "org@domain.com",
    ]
    for bad_org in malformed_orgs:
        with pytest.raises(HTTPException) as exc_info:
            verify_org_access({"org_id": bad_org})
        assert exc_info.value.status_code == 403
        assert "Malformed organization identifier" in exc_info.value.detail


def test_unknown_org_claim_fails_closed():
    """Verify that unauthorized organizations raise HTTP 403."""
    with pytest.raises(HTTPException) as exc_info:
        verify_org_access({"org_id": "attacker_syndicate_org"})
    assert exc_info.value.status_code == 403
    assert "not authorized to access this resource" in exc_info.value.detail


def test_development_env_allows_test_fixtures():
    """Verify that dev/test environment allows test fixture orgs like org_alpha and org_beta."""
    dev_settings = Settings(APP_ENV="development", ALLOWED_ORGS=None)
    allowed = get_effective_allowed_orgs(dev_settings)
    assert "org_alpha" in allowed
    assert "org_beta" in allowed
    assert "tenant_alpha" in allowed
    assert "vermithor" in allowed

    # verify_org_access succeeds with dev settings
    org = verify_org_access({"org_id": "org_alpha"}, allowed_orgs=allowed)
    assert org == "org_alpha"


def test_production_env_blocks_test_fixtures_by_default():
    """Verify that production environment strictly fails-closed against test orgs (org_alpha, org_beta)."""
    prod_settings = Settings(APP_ENV="production", ALLOWED_ORGS=None)
    prod_allowed = get_effective_allowed_orgs(prod_settings)

    # In production with default settings, test fixtures MUST NOT be authorized
    assert "org_alpha" not in prod_allowed
    assert "org_beta" not in prod_allowed
    assert "tenant_alpha" not in prod_allowed
    assert "vermithor" in prod_allowed
    assert "internal" in prod_allowed

    # verify_org_access fails for test orgs under production allowlist
    with pytest.raises(HTTPException) as exc_info:
        verify_org_access({"org_id": "org_alpha"}, allowed_orgs=prod_allowed)
    assert exc_info.value.status_code == 403
    assert "not authorized" in exc_info.value.detail

    # verify_org_access succeeds for production internal tenant
    assert verify_org_access({"org_id": "vermithor"}, allowed_orgs=prod_allowed) == "vermithor"


def test_production_env_allows_explicit_configured_orgs():
    """Verify that setting ALLOWED_ORGS via environment or config overrides production default."""
    prod_custom = Settings(APP_ENV="production", ALLOWED_ORGS="pilot-customer-alpha, vermithor-prod")
    custom_allowed = get_effective_allowed_orgs(prod_custom)

    assert "pilot-customer-alpha" in custom_allowed
    assert "vermithor-prod" in custom_allowed
    assert "org_alpha" not in custom_allowed

    assert verify_org_access({"org_id": "pilot-customer-alpha"}, allowed_orgs=custom_allowed) == "pilot-customer-alpha"


def test_is_org_authorized_helper():
    """Verify is_org_authorized correctly handles edge cases, empty values, and custom lists."""
    assert is_org_authorized(None) is False
    assert is_org_authorized("") is False
    assert is_org_authorized("   ") is False
    assert is_org_authorized("bad/org") is False
    assert is_org_authorized("evil_corp", allowed_orgs=["safe_org"]) is False
    assert is_org_authorized("safe_org", allowed_orgs=["safe_org"]) is True


def test_worker_investigation_task_rejects_unauthorized_org():
    """Verify Celery investigate_incident_task aborts when org_id is unauthorized or missing."""
    from backend.workers.tasks import investigate_incident_task

    # Missing org_id
    res1 = investigate_incident_task({"incident_key": "INC-TEST-001"})
    assert res1["status"] == "unauthorized"
    assert "Missing required organization" in res1["error"]

    # Unauthorized org
    res2 = investigate_incident_task({"incident_key": "INC-TEST-001", "org_id": "unauthorized_corp_x"})
    assert res2["status"] == "unauthorized"
    assert "not authorized to run investigations" in res2["error"]


def test_worker_repair_task_rejects_unauthorized_org():
    """Verify Celery repair_code_task aborts when org_id is unauthorized or missing."""
    from backend.workers.tasks import repair_code_task

    # Missing org_id
    res1 = repair_code_task({"investigation_key": "INV-TEST-001"})
    assert res1["status"] == "unauthorized"
    assert "Missing required organization" in res1["error"]

    # Unauthorized org
    res2 = repair_code_task({"investigation_key": "INV-TEST-001", "org_id": "unauthorized_corp_x"})
    assert res2["status"] == "unauthorized"
    assert "not authorized to run repairs" in res2["error"]
