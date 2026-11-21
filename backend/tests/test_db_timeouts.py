"""PostgreSQL connect-argument construction for statement/lock timeouts.

These are pure functions; no database connection is opened. The behaviour must
match what psycopg v3 accepts as libpq ``options`` and must not send startup
options to a PgBouncer-style pooled endpoint.
"""

from app.core import config
from app.core import database as database_module


def _connect_args(monkeypatch, url: str, **settings_overrides) -> dict:
    for key, value in settings_overrides.items():
        monkeypatch.setattr(config.settings, key, value)
    return database_module._postgres_connect_args(url)


def test_direct_endpoint_sets_statement_and_lock_timeouts(monkeypatch):
    args = _connect_args(
        monkeypatch,
        "postgresql+psycopg://u:p@db.example.com:5432/helpdesk",
        DB_STATEMENT_TIMEOUT_MS=15_000,
        DB_LOCK_TIMEOUT_MS=5_000,
    )

    assert args["connect_timeout"] == config.settings.DB_CONNECT_TIMEOUT_SECONDS
    assert args["options"] == ("-c statement_timeout=15000 -c lock_timeout=5000")
    assert "prepare_threshold" not in args


def test_zero_sends_explicit_zero_to_override_server_defaults(monkeypatch):
    """``0`` must be sent, not omitted.

    A database role with a server-side ``statement_timeout`` would otherwise
    keep that limit because PostgreSQL only replaces it when the client sends
    an explicit value.
    """
    args = _connect_args(
        monkeypatch,
        "postgresql+psycopg://u:p@db.example.com:5432/helpdesk",
        DB_STATEMENT_TIMEOUT_MS=0,
        DB_LOCK_TIMEOUT_MS=0,
    )

    assert args["options"] == "-c statement_timeout=0 -c lock_timeout=0"
    assert "connect_timeout" in args


def test_pooled_endpoint_skips_startup_options_but_keeps_prepared_fix(monkeypatch):
    args = _connect_args(
        monkeypatch,
        "postgresql+psycopg://u:p@ep-cool-name-123456-pooler.example.com:5432/db",
        DB_STATEMENT_TIMEOUT_MS=15_000,
        DB_LOCK_TIMEOUT_MS=5_000,
    )

    assert args["prepare_threshold"] is None
    assert "options" not in args


def test_production_rejects_negative_timeouts():
    import pytest

    from app.core.config import Settings

    with pytest.raises(RuntimeError, match="DB_STATEMENT_TIMEOUT_MS"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            DATABASE_URL=(
                "postgresql+psycopg://helpdesk:strongpass@"
                "postgres.railway.internal:5432/helpdesk"
            ),
            CLERK_SECRET_KEY="sk_live_" + "x" * 32,
            FRONTEND_URL="https://helpdesk.acme-corp.com",
            RATE_LIMIT_ENABLED=True,
            RATE_LIMIT_REDIS_URL=(
                "rediss://default:strongpass@redis.railway.internal:6379/0"
            ),
            RATE_LIMIT_TRUSTED_PROXIES="10.0.0.0/8",
            MALWARE_SCAN_ENABLED=False,
            ATTACHMENTS_ENABLED=False,
            DB_STATEMENT_TIMEOUT_MS=-1,
        )
