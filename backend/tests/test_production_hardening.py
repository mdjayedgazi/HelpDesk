"""Regression tests for the production-hardening pass.

Each test corresponds to a defect or control implemented in this change set:
explicit-null updates, whitespace-only input, status timestamps, configuration
validation, request/security limits, and notification-poll rate limiting.
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.api.routers.users import _profile_integrity_error
from app.core.config import Settings
from app.core.config import settings as app_settings
from app.core.logging import redact
from app.enums.enums import Role, TicketStatus


def _ticket_payload(**overrides):
    payload = {
        "title": "Hardening regression",
        "description": "The body is long enough to be meaningful.",
        "category": "TECHNICAL",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_ticket_patch_rejects_explicit_null_for_required_column(
    client, make_user, make_ticket
):
    customer = await make_user()
    agent = await make_user(role=Role.AGENT)
    ticket = await make_ticket(customer, assignee=agent)

    response = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers={"X-Test-User": agent.username},
        json={"title": None},
    )

    assert response.status_code == 422
    assert "title" in response.json()["detail"]


@pytest.mark.asyncio
async def test_ticket_patch_rejects_explicit_null_status(
    client, make_user, make_ticket
):
    customer = await make_user()
    agent = await make_user(role=Role.AGENT)
    ticket = await make_ticket(customer, assignee=agent)

    response = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers={"X-Test-User": agent.username},
        json={"status": None},
    )

    assert response.status_code == 422
    assert "status" in response.json()["detail"]


@pytest.mark.asyncio
async def test_profile_patch_rejects_explicit_null_and_whitespace(client, make_user):
    user = await make_user()

    explicit_null = await client.patch(
        "/api/v1/users/me",
        headers={"X-Test-User": user.username},
        json={"full_name": None},
    )
    assert explicit_null.status_code == 422

    whitespace = await client.patch(
        "/api/v1/users/me",
        headers={"X-Test-User": user.username},
        json={"full_name": "   "},
    )
    assert whitespace.status_code == 422


@pytest.mark.asyncio
async def test_owner_update_rejects_explicit_null_role(client, make_user):
    owner = await make_user(role=Role.OWNER)
    target = await make_user()

    response = await client.patch(
        f"/api/v1/users/{target.id}",
        headers={"X-Test-User": owner.username},
        json={"role": None},
    )

    assert response.status_code == 422
    assert "role" in response.json()["detail"]


@pytest.mark.asyncio
async def test_whitespace_only_ticket_and_comment_bodies_are_rejected(
    client, make_user, make_ticket
):
    customer = await make_user()
    ticket = await make_ticket(customer)

    bad_ticket = await client.post(
        "/api/v1/tickets",
        headers={"X-Test-User": customer.username},
        json=_ticket_payload(description=" \n\t "),
    )
    assert bad_ticket.status_code == 422

    bad_comment = await client.post(
        f"/api/v1/tickets/{ticket.id}/comments",
        headers={"X-Test-User": customer.username},
        json={"body": "   \n"},
    )
    assert bad_comment.status_code == 422


@pytest.mark.asyncio
async def test_resolved_to_closed_preserves_resolved_at(client, make_user, make_ticket):
    customer = await make_user()
    agent = await make_user(role=Role.AGENT)
    ticket = await make_ticket(
        customer, status=TicketStatus.IN_PROGRESS, assignee=agent
    )
    headers = {"X-Test-User": agent.username}

    resolved = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers=headers,
        json={"status": "RESOLVED"},
    )
    assert resolved.status_code == 200
    resolved_at = resolved.json()["resolved_at"]
    assert resolved_at is not None

    closed = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers=headers,
        json={"status": "CLOSED"},
    )
    assert closed.status_code == 200
    assert closed.json()["resolved_at"] == resolved_at


@pytest.mark.asyncio
async def test_reopening_resolved_ticket_clears_resolved_at(
    client, make_user, make_ticket
):
    customer = await make_user()
    agent = await make_user(role=Role.AGENT)
    ticket = await make_ticket(
        customer, status=TicketStatus.IN_PROGRESS, assignee=agent
    )
    headers = {"X-Test-User": agent.username}

    resolved = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers=headers,
        json={"status": "RESOLVED"},
    )
    assert resolved.json()["resolved_at"] is not None

    reopened = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers=headers,
        json={"status": "IN_PROGRESS"},
    )
    assert reopened.status_code == 200
    assert reopened.json()["resolved_at"] is None


def test_log_redaction_covers_credentials_and_connection_urls():
    message = (
        "Authorization: Bearer top-secret sk_live_abcdef "
        "postgresql+psycopg://user:strongpass@db.internal/helpdesk "
        "redis://default:redispass@cache.internal:6379/0 password=letmein"
    )

    redacted = redact(message)

    for secret in ("top-secret", "abcdef", "strongpass", "redispass", "letmein"):
        assert secret not in redacted
    assert "[REDACTED]" in redacted


def test_non_username_integrity_error_is_not_reported_as_username_conflict():
    email_conflict = IntegrityError(
        "UPDATE users SET email=%(email)s",
        {},
        Exception("UNIQUE constraint failed: users.email"),
    )
    mapped = _profile_integrity_error(email_conflict)
    assert mapped.status_code == 409
    assert mapped.detail == "Could not update the profile because of a data conflict"

    username_conflict = IntegrityError(
        "UPDATE users SET username=%(username)s",
        {},
        Exception("UNIQUE constraint failed: users.username"),
    )
    mapped_username = _profile_integrity_error(username_conflict)
    assert mapped_username.detail == "Username is already taken"


@pytest.mark.asyncio
async def test_ticket_update_requests_a_row_lock(
    client, make_user, make_ticket, monkeypatch
):
    from app.api.routers import tickets as tickets_router

    customer = await make_user()
    agent = await make_user(role=Role.AGENT)
    ticket = await make_ticket(customer, assignee=agent)
    original = tickets_router.load_visible_ticket
    lock_calls: list[bool] = []

    async def recording_load(*args, **kwargs):
        lock_calls.append(bool(kwargs.get("for_update")))
        return await original(*args, **kwargs)

    monkeypatch.setattr(tickets_router, "load_visible_ticket", recording_load)

    response = await client.patch(
        f"/api/v1/tickets/{ticket.id}",
        headers={"X-Test-User": agent.username},
        json={"priority": "HIGH"},
    )

    assert response.status_code == 200
    assert lock_calls == [True]


@pytest.mark.asyncio
async def test_security_headers_and_no_store_are_present(client, make_user):
    user = await make_user()

    api = await client.get("/api/v1/users/me", headers={"X-Test-User": user.username})
    assert api.status_code == 200
    assert api.headers["x-content-type-options"] == "nosniff"
    assert api.headers["x-frame-options"] == "DENY"
    assert api.headers["referrer-policy"] == "no-referrer"
    assert "camera=()" in api.headers["permissions-policy"]
    assert "default-src 'none'" in api.headers["content-security-policy"]
    assert api.headers["cache-control"] == "no-store"
    assert api.headers["x-request-id"]

    health = await client.get("/health/live")
    assert health.status_code == 200
    assert health.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_hsts_is_only_added_when_explicitly_enabled(client, monkeypatch):
    default = await client.get("/health/live")
    assert "strict-transport-security" not in default.headers

    monkeypatch.setattr(app_settings, "HSTS_ENABLED", True)
    enabled = await client.get("/health/live")
    assert enabled.status_code == 200
    assert "max-age=31536000" in enabled.headers["strict-transport-security"]


@pytest.mark.asyncio
async def test_oversized_json_body_is_rejected_before_parsing(client):
    response = await client.post(
        "/api/v1/tickets",
        content=b"{" + b"x" * (app_settings.MAX_JSON_BODY_BYTES + 1),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Request body is too large"
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_oversized_multipart_body_is_rejected_before_parsing(client, monkeypatch):
    monkeypatch.setattr(app_settings, "MAX_UPLOAD_BYTES", 10)
    monkeypatch.setattr(app_settings, "MAX_MULTIPART_OVERHEAD_BYTES", 5)

    response = await client.post(
        "/api/v1/tickets",
        content=b"x" * 16,
        headers={"Content-Type": "multipart/form-data; boundary=verify"},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Request body is too large"
    assert response.headers["x-content-type-options"] == "nosniff"


@pytest.mark.asyncio
async def test_oversized_chunked_body_is_stopped_before_spooling(client, monkeypatch):
    monkeypatch.setattr(app_settings, "MAX_UPLOAD_BYTES", 10)
    monkeypatch.setattr(app_settings, "MAX_MULTIPART_OVERHEAD_BYTES", 5)

    async def chunks():
        yield b"x" * 8
        yield b"x" * 8

    response = await client.post(
        "/api/v1/tickets",
        content=chunks(),
        headers={"Content-Type": "multipart/form-data; boundary=verify"},
    )

    assert response.status_code == 413
    assert response.json()["detail"] == "Request body is too large"


@pytest.mark.asyncio
async def test_health_readiness_checks_database(client):
    response = await client.get("/health/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["redis"] == "disabled"
    assert body["checks"]["clamav"] == "disabled"


@pytest.mark.asyncio
async def test_docs_remain_available_outside_production(client):
    response = await client.get("/docs")
    assert response.status_code == 200
    assert "swagger" in response.text.lower()


@pytest.mark.asyncio
async def test_attachment_count_quota_is_enforced(
    client, make_user, make_ticket, monkeypatch
):
    monkeypatch.setattr(app_settings, "MAX_ATTACHMENTS_PER_TICKET", 1)
    customer = await make_user()
    ticket = await make_ticket(customer)
    path = f"/api/v1/tickets/{ticket.id}/attachments"
    headers = {"X-Test-User": customer.username}

    first = await client.post(
        path,
        headers=headers,
        files={"file": ("one.txt", b"first", "text/plain")},
    )
    assert first.status_code == 201

    second = await client.post(
        path,
        headers=headers,
        files={"file": ("two.txt", b"second", "text/plain")},
    )
    assert second.status_code == 422
    assert "attachment count limit" in second.json()["detail"]


@pytest.mark.asyncio
async def test_attachment_byte_quota_is_enforced(
    client, make_user, make_ticket, monkeypatch
):
    monkeypatch.setattr(app_settings, "MAX_TICKET_ATTACHMENT_BYTES", 10)
    customer = await make_user()
    ticket = await make_ticket(customer)
    path = f"/api/v1/tickets/{ticket.id}/attachments"
    headers = {"X-Test-User": customer.username}

    response = await client.post(
        path,
        headers=headers,
        files={"file": ("too-big.txt", b"0123456789A", "text/plain")},
    )
    assert response.status_code == 413
    assert "storage limit" in response.json()["detail"]


def _production_settings(**overrides) -> Settings:
    values = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": (
            "postgresql+psycopg://helpdesk:strongpass@postgres.railway.internal:5432/helpdesk"
        ),
        "CLERK_SECRET_KEY": ('sk_live_' + 'x' * 32),
        "FRONTEND_URL": "https://helpdesk.acme-corp.com",
        "RATE_LIMIT_ENABLED": True,
        "RATE_LIMIT_REDIS_URL": "redis://default:strongpass@redis.railway.internal:6379/0",
        "RATE_LIMIT_TRUSTED_PROXIES": "0.0.0.0/0,::/0",
        "MALWARE_SCAN_ENABLED": True,
        "CLAMAV_HOST": "clamav.railway.internal",
        "UPLOAD_DIR": "/data/uploads",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_valid_production_configuration_is_accepted():
    config = _production_settings()

    assert config.is_production is True
    assert config.docs_enabled is False
    assert config.RATE_LIMIT_TRUSTED_PROXIES == ["0.0.0.0/0", "::/0"]
    assert config.max_upload_request_bytes == (
        config.MAX_UPLOAD_BYTES + config.MAX_MULTIPART_OVERHEAD_BYTES
    )


@pytest.mark.parametrize(
    ("override", "expected"),
    [
        ({"FRONTEND_URL": "http://localhost:5173"}, "FRONTEND_URL"),
        ({"FRONTEND_URL": "http://helpdesk.example.com"}, "FRONTEND_URL"),
        ({"FRONTEND_URL": "https://helpdesk.example.com"}, "placeholder"),
        ({"CLERK_SECRET_KEY": ('sk_test_' + 'x' * 32)}, "CLERK_SECRET_KEY"),
        ({"DATABASE_URL": "sqlite+aiosqlite://"}, "DATABASE_URL"),
        (
            {"DATABASE_URL": "postgresql+psycopg://u:p@localhost:5432/helpdesk"},
            "DATABASE_URL",
        ),
        ({"RATE_LIMIT_ENABLED": False}, "RATE_LIMIT_ENABLED"),
        (
            {"RATE_LIMIT_REDIS_URL": "redis://localhost:6379/0"},
            "RATE_LIMIT_REDIS_URL",
        ),
        ({"RATE_LIMIT_TRUSTED_PROXIES": ""}, "RATE_LIMIT_TRUSTED_PROXIES"),
        ({"RATE_LIMIT_REDIS_TIMEOUT_SECONDS": 0}, "RATE_LIMIT_REDIS_TIMEOUT_SECONDS"),
        ({"RATE_LIMIT_WINDOW_SECONDS": 0}, "RATE_LIMIT_WINDOW_SECONDS"),
        (
            {"RATE_LIMIT_ACCOUNT_REQUEST_WINDOW_SECONDS": 0},
            "RATE_LIMIT_ACCOUNT_REQUEST_WINDOW_SECONDS",
        ),
        ({"RATE_LIMIT_TICKET_CREATE": 0}, "RATE_LIMIT_TICKET_CREATE"),
        ({"MALWARE_SCAN_ENABLED": False}, "MALWARE_SCAN_ENABLED"),
        ({"CLAMAV_HOST": "127.0.0.1"}, "CLAMAV_HOST"),
        ({"CLAMAV_PORT": 0}, "CLAMAV_PORT"),
        ({"CLAMAV_TIMEOUT_SECONDS": 0}, "CLAMAV_TIMEOUT_SECONDS"),
        ({"HSTS_MAX_AGE_SECONDS": -1}, "HSTS_MAX_AGE_SECONDS"),
        ({"LOG_LEVEL": "LOUD"}, "LOG_LEVEL"),
        ({"UPLOAD_DIR": "uploads"}, "UPLOAD_DIR"),
        ({"UPLOAD_DIR": "/tmp/uploads"}, "UPLOAD_DIR"),
        ({"AUTO_CREATE_TABLES": True}, "AUTO_CREATE_TABLES"),
        ({"DATABASE_ECHO": True}, "DATABASE_ECHO"),
        ({"DB_POOL_SIZE": 0}, "DB_POOL_SIZE"),
        ({"DB_MAX_OVERFLOW": -1}, "DB_MAX_OVERFLOW"),
        ({"DB_POOL_TIMEOUT_SECONDS": 0}, "DB_POOL_TIMEOUT_SECONDS"),
        ({"DB_POOL_RECYCLE_SECONDS": -1}, "DB_POOL_RECYCLE_SECONDS"),
        ({"DB_CONNECT_TIMEOUT_SECONDS": 0}, "DB_CONNECT_TIMEOUT_SECONDS"),
        ({"DB_STATEMENT_TIMEOUT_MS": 0}, "DB_STATEMENT_TIMEOUT_MS"),
        (
            {"CORS_ORIGINS": "https://one.example.com,http://localhost:5173"},
            "CORS_ORIGINS",
        ),
        ({"CORS_ORIGINS": "*"}, "Wildcard"),
    ],
)
def test_invalid_production_configuration_fails_closed(override, expected):
    with pytest.raises(RuntimeError, match=expected):
        _production_settings(**override)


def test_production_configuration_error_never_echoes_secret_values():
    secret = "sk_test_super-secret-value"
    with pytest.raises(RuntimeError) as excinfo:
        _production_settings(CLERK_SECRET_KEY=secret)
    message = str(excinfo.value)
    assert "CLERK_SECRET_KEY" in message
    assert secret not in message
    assert "strongpass" not in message


def test_production_configuration_can_be_disabled_for_tests(tmp_path):
    local = Settings(
        _env_file=None,
        ENVIRONMENT="test",
        DATABASE_URL="sqlite+aiosqlite://",
        CLERK_SECRET_KEY="sk_test_dummy",
        FRONTEND_URL="http://localhost:5173",
        UPLOAD_DIR=str(tmp_path),
    )
    assert local.is_production is False
    assert local.docs_enabled is True


def test_short_production_configuration_rejects_placeholders(tmp_path):
    with pytest.raises(RuntimeError, match="placeholder"):
        _production_settings(
            DATABASE_URL=(
                "postgresql+psycopg://user:replace-me@postgres.railway.internal:5432/db"
            )
        )


def test_production_docs_routes_are_disabled_in_a_fresh_app_process():
    """The docs decision is made at import time, so verify it in a subprocess."""
    import os
    import subprocess
    import sys

    env = {
        **os.environ,
        "ENVIRONMENT": "production",
        "DB_STATEMENT_TIMEOUT_MS": "5000",
        "DATABASE_URL": (
            "postgresql+psycopg://helpdesk:strongpass@postgres.railway.internal:5432/helpdesk"
        ),
        "CLERK_SECRET_KEY": ('sk_live_' + 'x' * 32),
        "FRONTEND_URL": "https://helpdesk.acme-corp.com",
        "CORS_ORIGINS": "",
        "RATE_LIMIT_ENABLED": "true",
        "RATE_LIMIT_REDIS_URL": (
            "redis://default:strongpass@redis.railway.internal:6379/0"
        ),
        "RATE_LIMIT_TRUSTED_PROXIES": "0.0.0.0/0,::/0",
        "MALWARE_SCAN_ENABLED": "true",
        "CLAMAV_HOST": "clamav.railway.internal",
        "UPLOAD_DIR": "/data/uploads",
        "AUTO_CREATE_TABLES": "false",
    }
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.main import app; "
                "assert app.docs_url is None; "
                "assert app.openapi_url is None; "
                "assert app.redoc_url is None; "
                "print('docs-disabled')"
            ),
        ],
        cwd=os.getcwd(),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "docs-disabled" in completed.stdout
