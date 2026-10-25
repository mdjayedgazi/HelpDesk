# HelpDesk backend

FastAPI + SQLModel (async SQLAlchemy, PostgreSQL via psycopg v3) with Clerk
authentication.

## Setup

1. Create `backend/.env` from `.env.example` and fill in `CLERK_SECRET_KEY`
   and `DATABASE_URL`.
2. Install dependencies (the project uses [uv](https://docs.astral.sh/uv/)):

   ```bash
   uv sync
   ```

3. Apply database migrations:

   ```bash
   alembic upgrade head
   ```

   See [`migrations/README.md`](migrations/README.md) for the full migration
   workflow, including how to adopt an existing database.

   `AUTO_CREATE_TABLES` is disabled by default. It exists only as a local
   development convenience and must stay off in production: the schema is
   owned by Alembic.

## Run

```bash
uv run fastapi dev app/main.py
```

## Tests

```bash
uv run pytest -q
```

The tests run against an in-memory SQLite database with Clerk stubbed out, so
they need no external services.

Lint and formatting use the explicit policy in `pyproject.toml`:

```bash
uv run ruff check .
uv run ruff format --check .
```

### PostgreSQL integration tests

The PostgreSQL-only suites are skipped unless a disposable database URL is
provided. The database name must contain `test`, `verify`, or `ci`, and the
suites never truncate or drop data:

```bash
HD_TEST_POSTGRES_URL='postgresql+psycopg://verify:verify@127.0.0.1:55432/hdverify' \
    uv run pytest -q tests/test_postgres_integration.py
```

The demo-seed suite uses a separate, otherwise-empty database via
`HD_DEMO_SEED_POSTGRES_URL` (name must contain `verify`, `demo`, `test`, or
`ci`). See `tests/test_demo_seed_postgres.py` for the exact example. CI
(`.github/workflows/ci.yml`) runs both against disposable service containers.

The rate-limit integration test is skipped unless `HD_TEST_REDIS_URL` points at
a disposable Redis database:

```bash
HD_TEST_REDIS_URL='redis://127.0.0.1:56379/15' \
    uv run pytest -q tests/test_rate_limit.py -k redis_backend
```

## Malware scanning and upload quarantine

Uploads are fail-closed. `MALWARE_SCAN_ENABLED` defaults to `false`, which means
uploads return `503`; there is no "skip scan" mode. Configure a ClamAV daemon
over TCP:

```dotenv
MALWARE_SCAN_ENABLED=true
CLAMAV_HOST=127.0.0.1
CLAMAV_PORT=3310
CLAMAV_TIMEOUT_SECONDS=10
```

The upload is written to `UPLOAD_DIR/.quarantine`, scanned with ClamAV's
INSTREAM protocol, and moved into `UPLOAD_DIR` only after a `CLEAN` result.
Infected, timed-out, unavailable, or unknown results delete the file and reject
the upload. Downloads require `Attachment.scan_status == CLEAN`.

Migration `0009_attachment_scan_status` marks all pre-existing attachments
`PENDING`; they are not downloadable. After clamd is deployed, rescan them:

```bash
uv run python -m app.commands.scan_attachments
```

The command promotes clean files, deletes infected bytes, and leaves rows
`PENDING` if the scanner is unavailable.

## Rate limiting

Rate limiting is implemented but disabled by default because an in-process
counter is unsafe with multiple workers. Enable it only with a shared Redis:

```dotenv
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REDIS_URL=redis://127.0.0.1:6379/0
# Comma-separated proxy IPs/CIDRs; leave empty if the app is directly exposed.
RATE_LIMIT_TRUSTED_PROXIES=
```

Protected write endpoints return `429` with `Retry-After`. If Redis is missing
or unreachable, they fail closed with `503`. There is no in-memory fallback.
Tune the per-policy limits and windows in `.env.example`.
