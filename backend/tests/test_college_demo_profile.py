"""Tests for the explicit public college-demo deployment profile.

The profile may use Clerk development keys and run without ClamAV, but only
when attachments are disabled. These tests pin that boundary so the profile
cannot quietly become a way to weaken a standard production deployment.
"""

import uuid
from pathlib import Path

import pytest
from fastapi import Request

from app.core.config import Settings
from app.core.config import settings as app_settings
from app.core.database import _is_pooled_postgres
from app.core.rate_limit import rate_limit_scope


def _college_demo_settings(**overrides) -> Settings:
    values = {
        "ENVIRONMENT": "production",
        "DEPLOYMENT_PROFILE": "college-demo",
        "DATABASE_URL": (
            "postgresql+psycopg://helpdesk:strongpass@"
            "ep-demo-123-pooler.us-east-1.aws.neon.tech/helpdesk?sslmode=require"
        ),
        "CLERK_SECRET_KEY": "sk_test_" + "x" * 32,
        "FRONTEND_URL": "https://helpdesk-web-demo.up.railway.app",
        "RATE_LIMIT_ENABLED": True,
        "RATE_LIMIT_REDIS_URL": "rediss://default:strongpass@cache.upstash.io:6379",
        "RATE_LIMIT_TRUSTED_PROXIES": "",
        "ATTACHMENTS_ENABLED": False,
        "MALWARE_SCAN_ENABLED": False,
        "UPLOAD_DIR": "uploads",
        "DB_POOL_SIZE": 1,
        "DB_MAX_OVERFLOW": 0,
        "AUTO_CREATE_TABLES": False,
        "DATABASE_ECHO": False,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_valid_college_demo_configuration_is_accepted():
    config = _college_demo_settings()

    assert config.is_production is True
    assert config.is_college_demo is True
    assert config.docs_enabled is False
    assert config.ATTACHMENTS_ENABLED is False
    assert config.RATE_LIMIT_TRUSTED_PROXIES == []
    assert config.CLERK_SECRET_KEY.startswith("sk_test_")


def test_college_demo_does_not_relax_core_production_controls():
    with pytest.raises(RuntimeError, match="AUTO_CREATE_TABLES"):
        _college_demo_settings(AUTO_CREATE_TABLES=True)
    with pytest.raises(RuntimeError, match="RATE_LIMIT_ENABLED"):
        _college_demo_settings(RATE_LIMIT_ENABLED=False)
    with pytest.raises(RuntimeError, match="FRONTEND_URL"):
        _college_demo_settings(FRONTEND_URL="http://localhost:5173")
    with pytest.raises(RuntimeError, match="Wildcard"):
        _college_demo_settings(CORS_ORIGINS="*")


def test_college_demo_requires_tls_redis():
    with pytest.raises(RuntimeError, match="rediss"):
        _college_demo_settings(
            RATE_LIMIT_REDIS_URL="redis://default:strongpass@cache.upstash.io:6379"
        )


def test_college_demo_rejects_wildcard_trusted_proxies():
    with pytest.raises(RuntimeError, match="must not trust every address"):
        _college_demo_settings(RATE_LIMIT_TRUSTED_PROXIES="0.0.0.0/0,::/0")


def test_college_demo_cannot_enable_attachments_without_scanning():
    with pytest.raises(RuntimeError, match="MALWARE_SCAN_ENABLED"):
        _college_demo_settings(ATTACHMENTS_ENABLED=True, MALWARE_SCAN_ENABLED=False)


def test_enabling_attachments_requires_a_scanner_and_durable_upload_dir():
    with pytest.raises(RuntimeError, match="UPLOAD_DIR"):
        _college_demo_settings(
            ATTACHMENTS_ENABLED=True,
            MALWARE_SCAN_ENABLED=True,
            CLAMAV_HOST="clamav.internal",
            UPLOAD_DIR="uploads",
        )


def test_attachments_enabled_with_scanner_is_accepted_in_college_demo():
    config = _college_demo_settings(
        ATTACHMENTS_ENABLED=True,
        MALWARE_SCAN_ENABLED=True,
        CLAMAV_HOST="clamav.internal",
        UPLOAD_DIR="/data/uploads",
    )
    assert config.ATTACHMENTS_ENABLED is True


def test_standard_profile_still_rejects_development_clerk_keys():
    with pytest.raises(RuntimeError, match="CLERK_SECRET_KEY"):
        _college_demo_settings(DEPLOYMENT_PROFILE="standard")


def test_pooled_neon_detection():
    assert _is_pooled_postgres(
        "postgresql+psycopg://u:p@ep-demo-123-pooler.us-east-1.aws.neon.tech/db"
    )
    assert not _is_pooled_postgres(
        "postgresql+psycopg://u:p@ep-demo-123.us-east-1.aws.neon.tech/db"
    )
    assert not _is_pooled_postgres("sqlite+aiosqlite://")


def _request(client_host: str, forwarded_for: str | None = None) -> Request:
    headers = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/",
            "headers": headers,
            "client": (client_host, 12345),
        }
    )


def test_college_demo_anonymous_requests_share_a_global_bucket(monkeypatch):
    monkeypatch.setattr(app_settings, "DEPLOYMENT_PROFILE", "college-demo")
    monkeypatch.setattr(app_settings, "RATE_LIMIT_TRUSTED_PROXIES", [])

    first = _request("10.0.0.1", "198.51.100.7")
    second = _request("10.0.0.2", "203.0.113.9")

    assert rate_limit_scope(None, first) == "anonymous:global"
    assert rate_limit_scope(None, second) == "anonymous:global"


def test_standard_profile_still_ignores_forged_forwarded_headers(monkeypatch):
    monkeypatch.setattr(app_settings, "DEPLOYMENT_PROFILE", "standard")
    monkeypatch.setattr(app_settings, "RATE_LIMIT_TRUSTED_PROXIES", [])

    forged = _request("10.0.0.1", "198.51.100.7")
    assert rate_limit_scope(None, forged) == "ip:10.0.0.1"


def test_authenticated_requests_use_the_user_bucket_regardless_of_headers(monkeypatch):
    monkeypatch.setattr(app_settings, "DEPLOYMENT_PROFILE", "college-demo")
    monkeypatch.setattr(app_settings, "RATE_LIMIT_TRUSTED_PROXIES", [])

    user = type("User", (), {"id": uuid.uuid4()})()
    first = _request("10.0.0.1", "198.51.100.7")
    second = _request("10.0.0.2", "203.0.113.9")

    assert rate_limit_scope(user, first) == f"user:{user.id}"
    assert rate_limit_scope(user, second) == f"user:{user.id}"


@pytest.mark.asyncio
async def test_disabled_uploads_are_rejected_before_parsing(
    client, make_user, make_ticket, monkeypatch
):
    monkeypatch.setattr(app_settings, "ATTACHMENTS_ENABLED", False)
    customer = await make_user()
    ticket = await make_ticket(customer)
    path = f"/api/v1/tickets/{ticket.id}/attachments"

    response = await client.post(
        path,
        headers={"X-Test-User": customer.username},
        files={"file": ("note.txt", b"should never be stored", "text/plain")},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Attachments are disabled in this deployment"
    assert response.headers["x-content-type-options"] == "nosniff"

    upload_root = Path(app_settings.UPLOAD_DIR)
    stored = list(upload_root.rglob("*")) if upload_root.exists() else []
    assert [path for path in stored if path.is_file()] == []


@pytest.mark.asyncio
async def test_disabling_attachments_does_not_break_tickets_or_comments(
    client, make_user, make_ticket, monkeypatch
):
    monkeypatch.setattr(app_settings, "ATTACHMENTS_ENABLED", False)
    customer = await make_user()
    headers = {"X-Test-User": customer.username}

    created = await client.post(
        "/api/v1/tickets",
        headers=headers,
        json={
            "title": "Demo ticket",
            "description": "Attachments are disabled but tickets still work.",
            "category": "TECHNICAL",
        },
    )
    assert created.status_code == 201
    ticket_id = created.json()["id"]

    listed = await client.get(
        f"/api/v1/tickets/{ticket_id}/attachments", headers=headers
    )
    assert listed.status_code == 200
    assert listed.json() == []

    comment = await client.post(
        f"/api/v1/tickets/{ticket_id}/comments",
        headers=headers,
        json={"body": "A comment still works."},
    )
    assert comment.status_code == 201
