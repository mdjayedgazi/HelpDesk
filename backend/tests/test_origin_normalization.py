"""Origin normalization for CORS and Clerk's authorized-party check.

A browser ``Origin`` header and Clerk's ``azp`` claim never carry a trailing
slash or a redundant default port. ``Settings.allowed_origins`` must therefore
reduce configured values to the same exact origin, or every preflight and
Clerk verification fails while configuration validation still passes.
"""

import pytest

from app.core.config import Settings, _normalize_origin


def _settings(**overrides) -> Settings:
    values = {
        "ENVIRONMENT": "test",
        "DATABASE_URL": "sqlite+aiosqlite://",
        "CLERK_SECRET_KEY": "sk_test_dummy",
        "FRONTEND_URL": "http://localhost:5173",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://helpdesk.acme-corp.com", "https://helpdesk.acme-corp.com"),
        ("https://helpdesk.acme-corp.com/", "https://helpdesk.acme-corp.com"),
        ("https://helpdesk.acme-corp.com///", "https://helpdesk.acme-corp.com"),
        ("  https://helpdesk.acme-corp.com/  ", "https://helpdesk.acme-corp.com"),
        ("https://helpdesk.acme-corp.com:443", "https://helpdesk.acme-corp.com"),
        ("https://helpdesk.acme-corp.com:443/", "https://helpdesk.acme-corp.com"),
        ("https://helpdesk.acme-corp.com:8443/", "https://helpdesk.acme-corp.com:8443"),
        ("http://localhost:5173/", "http://localhost:5173"),
        ("http://localhost:80", "http://localhost"),
        ("HTTPS://App.Example.COM/", "https://app.example.com"),
    ],
)
def test_normalize_origin_produces_browser_origin(raw, expected):
    assert _normalize_origin(raw) == expected


def test_normalize_origin_leaves_paths_and_wildcards_untouched():
    # A path-bearing value must not be silently reduced to an origin: the
    # production validator has to reject it instead.
    assert (
        _normalize_origin("https://helpdesk.acme-corp.com/dashboard")
        == "https://helpdesk.acme-corp.com/dashboard"
    )
    assert _normalize_origin("https://helpdesk.acme-corp.com?x=1") == (
        "https://helpdesk.acme-corp.com?x=1"
    )
    assert _normalize_origin("*") == "*"


def test_allowed_origins_normalizes_frontend_and_cors_and_deduplicates():
    config = _settings(
        FRONTEND_URL="https://helpdesk.acme-corp.com/",
        CORS_ORIGINS=[
            "https://helpdesk.acme-corp.com",
            "https://admin.acme-corp.com/",
            "https://helpdesk.acme-corp.com:443",
        ],
    )

    assert config.allowed_origins == [
        "https://helpdesk.acme-corp.com",
        "https://admin.acme-corp.com",
    ]


def test_normalized_frontend_origin_matches_browser_origin():
    config = _settings(FRONTEND_URL="https://helpdesk.acme-corp.com/")

    # What a browser actually sends in the Origin header / Clerk azp claim.
    browser_origin = "https://helpdesk.acme-corp.com"
    assert browser_origin in config.allowed_origins


def test_production_accepts_a_trailing_slash_and_normalizes_it():
    config = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        DATABASE_URL=(
            "postgresql+psycopg://helpdesk:strongpass@postgres.railway.internal:5432/helpdesk"
        ),
        CLERK_SECRET_KEY="sk_live_" + "x" * 32,
        FRONTEND_URL="https://helpdesk.acme-corp.com/",
        RATE_LIMIT_ENABLED=True,
        RATE_LIMIT_REDIS_URL="rediss://default:strongpass@redis.railway.internal:6379/0",
        RATE_LIMIT_TRUSTED_PROXIES="10.0.0.0/8",
        MALWARE_SCAN_ENABLED=False,
        ATTACHMENTS_ENABLED=False,
    )

    assert config.allowed_origins == ["https://helpdesk.acme-corp.com"]


def test_production_rejects_a_path_bearing_origin():
    with pytest.raises(RuntimeError, match="FRONTEND_URL"):
        Settings(
            _env_file=None,
            ENVIRONMENT="production",
            DATABASE_URL=(
                "postgresql+psycopg://helpdesk:strongpass@postgres.railway.internal:5432/helpdesk"
            ),
            CLERK_SECRET_KEY="sk_live_" + "x" * 32,
            FRONTEND_URL="https://helpdesk.acme-corp.com/dashboard",
            RATE_LIMIT_ENABLED=True,
            RATE_LIMIT_REDIS_URL="rediss://default:strongpass@redis.railway.internal:6379/0",
            RATE_LIMIT_TRUSTED_PROXIES="10.0.0.0/8",
            MALWARE_SCAN_ENABLED=False,
            ATTACHMENTS_ENABLED=False,
        )
