# Production readiness: external configuration and operations

This document lists the production-readiness items that depend on services and
dashboards **outside this repository**. Code changes cannot complete them, and
the repository cannot verify them. Each section states what remains, why it
cannot be verified from the repository, the exact place to configure it, the
environment variables involved (names only — never values), and how to confirm
success.

For database backup/restore and monitoring, see
[`DATABASE_BACKUP_RESTORE.md`](./DATABASE_BACKUP_RESTORE.md). For the standard
deployment steps, see [`DEPLOYMENT.md`](./DEPLOYMENT.md).

## Status summary

| Item | Repository-side status | External status |
| --- | --- | --- |
| Database backup / PITR / restore drill | Runbook + safe restore procedure added | **EXTERNAL — unverified** |
| Clerk production instance | Code enforces `sk_live_` outside the demo profile; validation + tests added | **EXTERNAL — unverified** |
| Real readiness check | Implemented (`database` + `schema` + `redis` + `clamav`) with tests | Verified locally + disposable PostgreSQL |
| `FRONTEND_URL` trailing slash | Normalized for CORS and Clerk `azp`; tested | Code complete |
| Object storage for uploads | Analysed; **not implemented** (no provider access) | **EXTERNAL — decision required** |
| Redis ownership / durability | TLS required; fail-closed; document only | **EXTERNAL — unverified** |

## 1. Clerk production instance (EXTERNAL)

### The problem

The live college-demo deployment uses a Clerk **development** instance
(`sk_test_…` / `pk_test_…`, Frontend API `*.clerk.accounts.dev`). A development
instance is not appropriate for a long-lived production site: it has development
rate limits/branding and its keys are not production keys.

### What the code already enforces

- Outside `DEPLOYMENT_PROFILE=college-demo`, production startup **fails** unless
  `CLERK_SECRET_KEY` starts with `sk_live_`
  (`app/core/config.py::_validate_production_configuration`).
- Only the `college-demo` profile accepts `sk_test_`, and only because it is an
  explicitly public demo.
- `FRONTEND_URL` (and any `CORS_ORIGINS`) are normalized to exact browser
  origins and used both for CORS and Clerk's authorized-party (`azp`) check, so
  a trailing slash can no longer cause a silent mismatch.

### What remains (requires Clerk dashboard access)

1. Create/own a **production** Clerk instance for the real domain.
2. In that instance, configure allowed origins / redirect URLs for the exact
   frontend origin (for example `https://helpdesk.acme-corp.com`).
3. Set the following **without pasting secrets into source, chat, or logs**:
   - Backend service (Railway `helpdesk-api`): `CLERK_SECRET_KEY` = production
     `sk_live_…` key. Use the platform's secret UI or
     `railway variable set CLERK_SECRET_KEY --stdin --skip-deploys`.
   - Frontend build args (Railway `helpdesk-web`): `VITE_CLERK_PUBLISHABLE_KEY`
     = production `pk_live_…` key. This is a public key but must be the one that
     matches the production secret.
   - Frontend runtime: `CLERK_FAPI_ORIGIN` = the production Frontend API origin
     if it is a custom domain.
4. Rebuild and redeploy the frontend (the publishable key is baked into the
   bundle), then redeploy the backend.
5. Keep `DEPLOYMENT_PROFILE=standard` for a commercial deployment; do not keep
   `college-demo` in production.

### How to verify

- `GET /health/ready` returns `200` after redeploy.
- The browser console shows Clerk loading from the **production** Frontend API
  origin, with no CSP violations.
- A real sign-in succeeds and the redirect returns to the configured origin.
- The token's `azp` matches `FRONTEND_URL` (no CORS/preflight errors in the
  network tab).

Do not change live Railway credentials without the owner's authorization and
access to the production Clerk instance.

## 2. Redis ownership, TLS, and durability (EXTERNAL)

### What the code already enforces

- `RATE_LIMIT_REDIS_URL` must be `redis://` or `rediss://`; production refuses
  to start without it and without `RATE_LIMIT_ENABLED=true`.
- The college-demo profile requires **TLS** (`rediss://`).
- Connection, socket, and ping failures are fail-closed: protected endpoints
  return `503`, startup fails if Redis is unreachable, and `/health/ready`
  reports `redis: error`.
- The client sets explicit connect/socket timeouts
  (`RATE_LIMIT_REDIS_TIMEOUT_SECONDS`) and never logs the URL.

### Ownership and durability (requires Upstash account access)

The current Redis is an **Upstash** instance created through a no-signup flow;
such databases expire unless **claimed**. Ownership and durability must be
confirmed in the Upstash console:

1. **Claim the database** (if it is still a temporary no-signup database) so it
   is not deleted. Store the claim link outside the repository; do not commit it.
2. Confirm the database is on the intended **plan** with the expected
   **region** and **TLS enabled**.
3. Review **eviction / maxmemory policy**. Rate-limit counters are short-lived
   and losing them is safe (counters reset); do **not** rely on this Redis for
   application data. If the account offers persistence, its exact capabilities
   must be read from the Upstash console — this repository does not change
   eviction or persistence settings.
4. Record the owner and billing responsibility outside the repository.

Do not run `FLUSHALL`/`FLUSHDB` or change eviction/persistence without verifying
the actual Upstash capabilities and owner approval.

### How to verify

- `GET /health/ready` shows `redis: ok`.
- The value's scheme is `rediss://` and the host is not localhost.
- After a redeploy, rate-limited endpoints still return the rate-limit headers
  (`X-RateLimit-*`) and a deliberate burst returns `429`.

Never print `RATE_LIMIT_REDIS_URL` or its password.

## 3. Object storage for uploads (DECISION / EXTERNAL)

### Current state (verified)

- Uploads are stored on a **single local volume** (`UPLOAD_DIR`, for example
  `/data/uploads`). `helm/values.yaml`, `docs/DEPLOYMENT.md`, and the backend
  config comment all state this and warn against multi-replica deployments.
- The upload path preserves the security controls that must not regress:
  magic-byte validation, ClamAV **fail-closed** scanning, quarantine → publish,
  path containment on download, and per-ticket quotas/authorization.
- The college-demo profile disables attachments entirely.

### Why object storage is not implemented here

Moving to S3/R2 requires a provider account, credentials, bucket policy, and a
migration of existing files. That access is not available to this change set, so
no half-finished storage backend was added. The storage abstraction currently
lives in `app/api/routers/attachments.py` (`_upload_root`, `_quarantine_root`,
and the single `FileResponse` download).

### Safe interim rule (enforced by documentation, not code)

**Do not run more than one backend replica while uploads are volume-local.**
`backend.replicaCount` and the Helm defaults stay at `1`. Redis is shared and is
not a substitute for file storage.

### If/when object storage is approved

1. Provision an S3-compatible bucket (AWS S3 or Cloudflare R2) with a private
   bucket policy and server-side encryption.
2. Provide credentials via the secret store only:
   - `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`,
     `S3_SECRET_ACCESS_KEY` (names only; never commit values).
3. Implement storage behind the existing upload/scan/download flow so the
   **quarantine → scan → publish** order and fail-closed semantics are
   unchanged, then migrate existing files with a one-off job that verifies
   checksums.
4. Only after the migration is verified should `replicaCount` be raised.

Until then, keep a single replica and a durable volume.

## 4. Frontend/backend request timeouts (implemented)

- The frontend API client now enforces a default request timeout
  (`DEFAULT_REQUEST_TIMEOUT_MS`, 20 s) and a longer upload timeout
  (`DEFAULT_UPLOAD_TIMEOUT_MS`, 120 s), combining the caller's `AbortSignal` with
  an internal `AbortController`. A hung request surfaces a clear message instead
  of spinning forever; genuine cancellations still reject with `AbortError`.
- The backend applies PostgreSQL `statement_timeout` and `lock_timeout` on
  **direct** endpoints (`DB_STATEMENT_TIMEOUT_MS`, `DB_LOCK_TIMEOUT_MS`), so one
  pathological query cannot pin a pooled connection. Pooled endpoints
  (PgBouncer/Neon `-pooler`) ignore per-connection startup options; set the same
  limits on the database role there.

## 5. Readiness semantics (implemented)

`GET /health/ready` now checks, cheaply and read-only:

- `database`: connectivity (`SELECT 1`).
- `schema`: the required core tables exist **and** the live
  `alembic_version` equals the migration head shipped in the image. In
  production a non-`ok` schema makes readiness return `503`; in development/test
  (where tables may come from `AUTO_CREATE_TABLES`) it is reported but not fatal.
- `redis` / `clamav`: enabled dependency reachability.

`GET /health/live` is unchanged and remains a pure liveness check. Readiness
never returns connection strings, hosts, or exception text.
