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
`PENDING`. A `PENDING` attachment is rescanned on demand at download time; the
file is served only after an explicit `CLEAN` result. After clamd is deployed,
rescan the whole backlog in one pass:

```bash
uv run python -m app.commands.scan_attachments
```

The command promotes clean files, deletes infected bytes, and leaves rows
`PENDING` if the scanner is unavailable. A scanner failure at download time
returns `503` and never serves the file.

## Rate limiting

Rate limiting is implemented but disabled by default because an in-process
counter is unsafe with multiple workers. Enable it only with a shared Redis:

```dotenv
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REDIS_URL=redis://127.0.0.1:6379/0
# Comma-separated proxy IPs/CIDRs; leave empty if the app is directly exposed.
RATE_LIMIT_TRUSTED_PROXIES=
```

Protected write endpoints and notification polling return `429` with
`Retry-After`. If Redis is missing or unreachable, they fail closed with `503`.
There is no in-memory fallback. Tune the per-policy limits and windows in
`.env.example`.

## Production mode

Set `ENVIRONMENT=production` for a deployed instance. In that mode the
application fails closed at startup unless:

- `FRONTEND_URL` and any `CORS_ORIGINS` are exact HTTPS origins (no localhost or
  placeholder values);
- `CLERK_SECRET_KEY` is a Clerk production secret (`sk_live_...`);
- `DATABASE_URL` and `RATE_LIMIT_REDIS_URL` use non-local PostgreSQL and Redis;
- `RATE_LIMIT_ENABLED=true`, `MALWARE_SCAN_ENABLED=true`, and
  `CLAMAV_HOST` is set;
- `UPLOAD_DIR` is an absolute, durable path on a mounted volume;
- `AUTO_CREATE_TABLES=false` and `DATABASE_ECHO=false`.

The error message names the invalid variables but never includes secret values.
See `../docs/DEPLOYMENT.md` for the complete Railway runbook, variables, volume,
migration command, and smoke tests.

## Health and readiness

| Endpoint | Meaning |
| --- | --- |
| `GET /health` and `GET /health/live` | The process can answer HTTP. Works during startup. |
| `GET /health/ready` | PostgreSQL, the enabled Redis limiter, and the enabled ClamAV scanner are reachable. Returns `503` with coarse check names when a dependency is unavailable. |

Use `/health/ready` as the load-balancer/traffic health check and
`/health/live` only for process liveness. Readiness deliberately fails if
malware scanning is enabled but ClamAV is unreachable; uploads are fail-closed
in that state.

## HTTP hardening

`app/core/middleware.py` rejects oversized JSON bodies (1 MB default) and
multipart requests (`MAX_UPLOAD_BYTES + MAX_MULTIPART_OVERHEAD_BYTES`) before
FastAPI parses or spools them. It also adds:

- security headers (`X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Permissions-Policy`, CSP, optional HSTS);
- `Cache-Control: no-store` for API responses;
- request IDs and structured, redacted request logs.

Swagger/ReDoc and `/openapi.json` are disabled when `ENVIRONMENT=production`.
Per-ticket attachment count and byte quotas are enforced in addition to the
per-file cap; see `MAX_ATTACHMENTS_PER_TICKET` and
`MAX_TICKET_ATTACHMENT_BYTES` in `.env.example`.

## Database timeouts

PostgreSQL connections use the pool and connect timeout settings documented in
`.env.example` (`DB_POOL_*`, `DB_CONNECT_TIMEOUT_SECONDS`). Migrations remain
the only supported schema mechanism in production; `AUTO_CREATE_TABLES` is a
local convenience only.
