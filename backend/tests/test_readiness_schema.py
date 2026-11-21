"""Readiness schema checks: healthy, outdated, incomplete, unknown, and fatal.

These tests use disposable in-memory SQLite databases. They never touch the
project database; the production probe simply uses the application engine.
"""

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel

import app.models  # noqa: F401  (registers every table on metadata)
from app.core import health as health_module

_ALEMBIC_VERSION_DDL = (
    "CREATE TABLE alembic_version (version_num VARCHAR(64) NOT NULL PRIMARY KEY)"
)


@pytest_asyncio.fixture
async def schema_engine():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
        await connection.execute(text(_ALEMBIC_VERSION_DDL))
    yield engine
    await engine.dispose()


async def _set_revision(engine, revision: str) -> None:
    async with engine.begin() as connection:
        await connection.execute(text("DELETE FROM alembic_version"))
        await connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": revision},
        )


@pytest.mark.asyncio
async def test_schema_status_is_ok_when_revision_matches(schema_engine, monkeypatch):
    await _set_revision(schema_engine, "0009_attachment_scan_status")
    monkeypatch.setattr(
        health_module,
        "expected_schema_revision",
        lambda: "0009_attachment_scan_status",
    )

    async with schema_engine.connect() as connection:
        assert await health_module.schema_status(connection) == "ok"


@pytest.mark.asyncio
async def test_schema_status_is_outdated_when_revision_differs(
    schema_engine, monkeypatch
):
    await _set_revision(schema_engine, "0001_initial")
    monkeypatch.setattr(
        health_module,
        "expected_schema_revision",
        lambda: "0009_attachment_scan_status",
    )

    async with schema_engine.connect() as connection:
        assert await health_module.schema_status(connection) == "outdated"


@pytest.mark.asyncio
async def test_schema_status_is_incomplete_when_a_table_is_missing(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.execute(text(_ALEMBIC_VERSION_DDL))
        await connection.execute(
            text(
                "INSERT INTO alembic_version (version_num) VALUES "
                "('0009_attachment_scan_status')"
            )
        )
    monkeypatch.setattr(
        health_module,
        "expected_schema_revision",
        lambda: "0009_attachment_scan_status",
    )

    try:
        async with engine.connect() as connection:
            assert await health_module.schema_status(connection) == "incomplete"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_schema_status_is_unknown_without_a_migration_head(
    schema_engine, monkeypatch
):
    monkeypatch.setattr(health_module, "expected_schema_revision", lambda: None)

    async with schema_engine.connect() as connection:
        assert await health_module.schema_status(connection) == "unknown"


def test_expected_revision_matches_the_shipped_migration_head():
    """The probe must read the real, single Alembic head from this checkout."""
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from app.core.health import _ALEMBIC_INI

    heads = ScriptDirectory.from_config(Config(str(_ALEMBIC_INI))).get_heads()

    assert len(heads) == 1
    assert health_module.expected_schema_revision() == heads[0]


def test_schema_failure_is_fatal_only_in_production(monkeypatch):
    monkeypatch.setattr(health_module.settings, "ENVIRONMENT", "test")
    assert health_module.schema_failure_is_fatal("outdated") is False
    assert health_module.schema_failure_is_fatal("incomplete") is False

    monkeypatch.setattr(health_module.settings, "ENVIRONMENT", "production")
    assert health_module.schema_failure_is_fatal("outdated") is True
    assert health_module.schema_failure_is_fatal("incomplete") is True
    assert health_module.schema_failure_is_fatal("unknown") is True
    assert health_module.schema_failure_is_fatal("ok") is False


@pytest.mark.asyncio
async def test_readiness_fails_for_a_bad_schema_in_production(monkeypatch):
    async def fake_schema_check() -> str:
        return "outdated"

    monkeypatch.setattr(health_module, "_schema_check", fake_schema_check)
    monkeypatch.setattr(health_module.settings, "ENVIRONMENT", "production")

    healthy, statuses = await health_module.readiness()

    assert healthy is False
    assert statuses["schema"] == "outdated"


@pytest.mark.asyncio
async def test_readiness_reports_but_tolerates_bad_schema_outside_production(
    monkeypatch,
):
    async def fake_schema_check() -> str:
        return "outdated"

    monkeypatch.setattr(health_module, "_schema_check", fake_schema_check)
    monkeypatch.setattr(health_module.settings, "ENVIRONMENT", "test")

    healthy, statuses = await health_module.readiness()

    assert healthy is True
    assert statuses["schema"] == "outdated"


@pytest.mark.asyncio
async def test_health_ready_returns_503_for_bad_schema_in_production(
    client, monkeypatch
):
    async def fake_schema_check() -> str:
        return "incomplete"

    monkeypatch.setattr(health_module, "_schema_check", fake_schema_check)
    monkeypatch.setattr(health_module.settings, "ENVIRONMENT", "production")

    response = await client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "unavailable"
    assert body["checks"]["schema"] == "incomplete"
    # No connection string, host, or exception text is ever exposed.
    assert "postgres" not in response.text.lower()
    assert "sqlite" not in response.text.lower()


@pytest.mark.asyncio
async def test_health_live_is_unaffected_by_schema_state(client, monkeypatch):
    async def fake_schema_check() -> str:
        return "incomplete"

    monkeypatch.setattr(health_module, "_schema_check", fake_schema_check)
    monkeypatch.setattr(health_module.settings, "ENVIRONMENT", "production")

    response = await client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
