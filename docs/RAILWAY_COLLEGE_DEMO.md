# Railway college-demo deployment

This document describes the **public college-demo deployment** of HelpDesk on
Railway's Free plan. It is a deliberately reduced profile: two services, an
external Neon PostgreSQL database, an external Upstash Redis instance, a Clerk
**development** instance, and attachments disabled because no malware scanner
runs in this profile.

It is a demo, not a commercial production deployment. The commercial profile is
still described in [`DEPLOYMENT.md`](./DEPLOYMENT.md); the differences are
listed in [Limitations](#limitations) and [Upgrade path](#upgrade-path).

No secrets appear in this document. Values below are variable **names** and
public URLs only.

## What this PR changes

PR #18 adds the demo profile and the deployment fixes it needs, without
migrating the application or weakening the standard production profile:

- `DEPLOYMENT_PROFILE=college-demo`, production validation, and an
  `ATTACHMENTS_ENABLED` kill-switch that rejects uploads before multipart
  parsing.
- Neon pooled-endpoint handling (no psycopg prepared statements) and an optional
  `MIGRATION_DATABASE_URL`.
- A conservative global anonymous rate-limit bucket when Railway proxy ranges
  are not verified; authenticated limits remain keyed by user id.
- Longer readiness probe timeouts for Neon cold starts.
- Two frontend CSP fixes so Clerk can load on the Railway domain.
- This runbook and the review in [`data.md`](../data.md).

It does not change the database schema, does not add a Railway service or
volume, and does not enable attachments.

## Architecture

```
Browser
  │  HTTPS
  ├──────────────► helpdesk-web (Railway, Nginx, :8080)
  │                  • serves the Vite/React SPA
  │                  • /healthz
  │                  • CSP allows only the API + Clerk origins
  │
  └──────────────► helpdesk-api (Railway, Uvicorn/FastAPI, :8080 via $PORT)
                     • Clerk session verification
                     • SQLModel/SQLAlchemy async + psycopg v3
                     • Redis rate limiting (fail closed)
                     • /health/live, /health/ready
                          │                    │
                          ▼                    ▼
                   Neon PostgreSQL        Upstash Redis
                   (pooled endpoint,      (rediss:// TLS,
                    TLS required)          external)
```

- The frontend never proxies API traffic. Its compiled bundle calls the public
  API origin directly, and that origin is also allowed by CORS and by the
  Nginx `connect-src` CSP directive.
- The API is stateless apart from PostgreSQL and Redis. There is no volume and
  no ClamAV service, because attachments are disabled.
- Exactly two Railway services exist. PostgreSQL and Redis are external, so
  they do not consume Railway Free-plan services or volumes.

## Railway Free-plan constraints

| Constraint | Consequence for this deployment |
| --- | --- |
| $1 of free credit per month | Services are tiny and sleep when idle. Keep usage inside the monthly credit and monitor **Usage**; this demo does not rely on paid overage. |
| 0.5 GB RAM / 1 vCPU per service | One API worker and one replica. The backend uses a small DB pool (`DB_POOL_SIZE=1`, `DB_MAX_OVERFLOW=0`). |
| Sleeping applications | Both services set `sleepApplication=true`. The first request after idle can take several seconds (cold start). Readiness allows 10 s per dependency probe. |
| One replica per service | Compatible with the current design because there are no local uploads on the API container. |
| No volume needed | No Railway volume is attached to either service. The pre-existing detached `redis-volume` is unrelated and untouched. |

## Railway configuration

Project: **helpdesk-college-demo** (reused from the account's only existing
empty project). Environment: **production**. Region: `ams`.

| Setting | `helpdesk-api` | `helpdesk-web` |
| --- | --- | --- |
| Source repo | `mdjayedgazi/HelpDesk` | `mdjayedgazi/HelpDesk` |
| Branch | `main` (after the PR merges) | `main` (after the PR merges) |
| Root directory | `/backend` | `/frontend` |
| Dockerfile | `Dockerfile` | `Dockerfile` |
| Watch pattern | `backend/**` | `frontend/**` |
| Healthcheck | `/health/live` | `/healthz` |
| Healthcheck timeout | 300 s | 300 s |
| Container port | `$PORT` (Railway injects `8080`) | `8080` |
| Public domain target port | must equal `$PORT` (`8080`) | `8080` |
| Replicas | 1 | 1 |
| Sleep when idle | on | on |
| Volume | none | none |
| Automatic deploys | on | on |

The services intentionally do **not** use `railway.toml`/`railway.json`; the
configuration lives in the Railway service settings.

**Port alignment matters.** The API image sets `PORT=8000` as a local default,
but Railway injects its own `PORT` (observed `8080`) at runtime. The public
service domain must target that same port. A domain target port of `8000`
against a container listening on `8080` leaves the deployment `SUCCESS` and the
container healthy, while every public request returns `502` or hangs at the
Railway edge. Confirm the running port in the startup log
(`Uvicorn running on http://0.0.0.0:<port>`) and check the service domain's
target port whenever the API is unreachable but `/health/live` passes from
Railway's own healthcheck.

`/health/live` is the **deployment gate**: it answers as soon as the process can
serve HTTP, so a slow Neon or Redis wake-up does not fail an otherwise healthy
release. `/health/ready` is the dependency probe and is monitored separately
after the deployment is live. Railway does not poll a healthcheck continuously.

Both deployment triggers are also set to **Wait for CI** (`checkSuites=true`),
so a push to `main` that fails any required GitHub check is not deployed.

### Status at 2026-11-17 (before PR #18 merge)

This section records the state of the live project while the PR is still open.
It is expected to change after the merge.

- `helpdesk-web` is **online**, but its active deployment predates the CSP fix
  in this PR. Its CSP currently contains empty placeholders where the Clerk
  Frontend API origin should be, so Clerk JavaScript is blocked and sign-in
  does not work on the public web domain. A redeploy from `main` is required.
- `helpdesk-api` has **no active deployment**. The last attempt failed because
  Railway built the repository root with Railpack before the service root was
  changed to `/backend`. Its public domain currently returns a Railway
  `404 "Application not found"`.
- Both services are now configured for Dockerfile builds from `/backend` and
  `/frontend`. The next deployment must come from `main` after PR #18 merges;
  do not deploy the PR branch directly.
- `RATE_LIMIT_REDIS_URL` is still **missing** on `helpdesk-api`. The API cannot
  pass production configuration validation or start until a working
  `rediss://` Upstash URL is added. See [Upstash Redis](#upstash-redis).

### Domains

Railway-generated HTTPS domains are used; no domain was purchased.

| Service | Public URL |
| --- | --- |
| API | `https://helpdesk-api-production-1dc9dd39.up.railway.app` |
| Web | `https://helpdesk-web-production-d96f8e2b.up.railway.app` |

Both domains are Railway `service` domains with `ACTIVE` TLS sync.

## Backend variables

These are the names required on `helpdesk-api`. One is currently pending:
`RATE_LIMIT_REDIS_URL` must be added before the API can start. Secret values
are streamed, never pasted into a command line or committed.

| Variable | Value in this deployment | Notes |
| --- | --- | --- |
| `ENVIRONMENT` | `production` | Enables fail-closed checks and disables API docs. |
| `DEPLOYMENT_PROFILE` | `college-demo` | The only profile that accepts `sk_test_` and scanner-free operation, and only with attachments disabled. |
| `DATABASE_URL` | *secret* — Neon pooled URL with `sslmode=require` | Not printed or committed. |
| `CLERK_SECRET_KEY` | *secret* — Clerk development `sk_test_…` | Streamed via stdin. |
| `FRONTEND_URL` | `https://helpdesk-web-production-d96f8e2b.up.railway.app` | Exact origin for CORS and Clerk `azp` checks. |
| `AUTO_CREATE_TABLES` | `false` | Schema is owned by Alembic. |
| `DATABASE_ECHO` | `false` | Do not log SQL containing data. |
| `RATE_LIMIT_ENABLED` | `true` | Rate limiting is mandatory. |
| `RATE_LIMIT_REDIS_URL` | *secret* — Upstash `rediss://…` **(not yet set)** | **Required.** TLS is required by the demo profile, and the API refuses to start without a reachable store. |
| `ATTACHMENTS_ENABLED` | `false` | Uploads rejected before multipart parsing; no unscanned files. |
| `MALWARE_SCAN_ENABLED` | `false` | Permitted **only** because attachments are disabled. |
| `DB_POOL_SIZE` | `1` | Fits the 0.5 GB instance and Neon connection limits. |
| `DB_MAX_OVERFLOW` | `0` | No burst connections beyond the pool. |
| `LOG_LEVEL` | `INFO` | |
| `LOG_JSON` | `true` | Structured logs with redaction. |
| `HSTS_ENABLED` | `false` | No API custom domain; Railway terminates TLS. |

Deliberately **not** set:

- `RATE_LIMIT_TRUSTED_PROXIES` — the Railway edge CIDRs were not verified for
  this service. Without a trusted range the limiter uses one shared
  `anonymous:global` bucket for unauthenticated callers instead of trusting an
  `X-Forwarded-For` header. Authenticated writes remain keyed by user id.
- `CORS_ORIGINS` — only `FRONTEND_URL` is allowed.
- `UPLOAD_DIR`, `CLAMAV_HOST`, `CLAMAV_PORT` — no attachments and no scanner.
- `MIGRATION_DATABASE_URL` — Neon is already at the migration head; no pending
  migrations were applied.
- `CLERK_WEBHOOK_SECRET`, `CLERK_JWKS_URL`, `DB_STATEMENT_TIMEOUT_MS` — unused by
  the running code.

## Frontend variables

`VITE_*` values are **compile-time** build arguments baked into the bundle. Any
change requires a redeploy, not a container restart. The other values are read
at container start by Nginx.

| Variable | Value | Kind |
| --- | --- | --- |
| `VITE_API_URL` | `https://helpdesk-api-production-1dc9dd39.up.railway.app` | build |
| `VITE_CLERK_PUBLISHABLE_KEY` | *secret-ish* — Clerk development `pk_test_…` | build |
| `VITE_ATTACHMENTS_ENABLED` | `false` | build |
| `API_ORIGIN` | same as `VITE_API_URL` | runtime |
| `CLERK_FAPI_ORIGIN` | `https://social-ferret-6540.clerk.accounts.dev` | runtime |
| `PORT` | `8080` | runtime |
| `HSTS_ENABLED` | `false` (enable only after HTTPS verification) | runtime |

`CLERK_FAPI_ORIGIN` is set explicitly to the Clerk development Frontend API
host. If it is omitted, `docker-entrypoint.sh` defaults it to
`https://*.clerk.accounts.dev`; in both cases the entrypoint **exports** the
value so `envsubst` can substitute it into the Nginx CSP. Without that export,
the placeholder is silently replaced with an empty string and Clerk is blocked
by the browser.

## Secure secret handling

Secret values are not included in this document and are not committed. They are
streamed from the local environment/environment file into Railway over stdin:

```bash
# Shape only — never paste a real value into a shell command.
railway variable set DATABASE_URL --stdin --service helpdesk-api --skip-deploys
railway variable set CLERK_SECRET_KEY --stdin --service helpdesk-api --skip-deploys
railway variable set RATE_LIMIT_REDIS_URL --stdin --service helpdesk-api --skip-deploys
railway variable set VITE_CLERK_PUBLISHABLE_KEY --stdin --service helpdesk-web --skip-deploys
```

Rules to follow:

1. Do not use `railway variable list` or the CLI's variable table for secret
   inspection; both print values. Query presence separately if needed.
2. `.env` files stay git-ignored and are parsed locally, never `cat`-ed.
3. Values are validated by their scheme/host shape (for example
   `rediss://…upstash.io`) without printing the credential.
4. Build logs and CI logs are not given secrets; Railway injects build
   arguments from its own variable store.
5. `VITE_CLERK_PUBLISHABLE_KEY` is public by design, but it is still not
   committed and is injected at build time.

## Neon PostgreSQL

- Neon server version: PostgreSQL 18.7.
- The runtime URL uses the `-pooler` host with `sslmode=require`.
- `backend/app/core/database.py` detects `-pooler` hostnames and sets
  `prepare_threshold=None` on psycopg v3. Neon's PgBouncer runs in transaction
  mode, where psycopg's automatic named prepared statements can collide between
  clients.
- `MIGRATION_DATABASE_URL` is supported so Alembic can use a direct endpoint if
  a future migration needs it. It is currently unset.
- Alembic revision at deployment time: `0009_attachment_scan_status` (head).
  There were **no pending migrations**, so no migration was run and no schema
  change was made.
- Existing data (1 user, 0 tickets, 0 comments, 0 attachments) was left intact.
  Nothing was deleted or reset.

Connection budget: with `DB_POOL_SIZE=1` and `DB_MAX_OVERFLOW=0`, one API
instance holds one application connection. Neon's Free plan connection limits
are not at risk.

## Upstash Redis

- Create a free Upstash Redis database in the same region if possible, enable
  TLS, and copy its `rediss://` URL.
- Set it without exposing the value:

  ```bash
  railway variable set RATE_LIMIT_REDIS_URL --stdin \
    --service helpdesk-api --skip-deploys
  ```

- `RATE_LIMIT_REDIS_URL` must be a `rediss://` URL; the demo profile rejects
  plaintext Redis in production.
- This variable is **currently missing** on the Railway service. Production
  configuration validation rejects the empty value, and the FastAPI lifespan
  also pings Redis before serving traffic, so the API cannot start until it is
  configured with a reachable database.
- Upstash is external to Railway, so it survives Railway redeploys and does not
  add a Railway service or volume.
- When Redis is unreachable, startup fails, protected endpoints fail closed with
  `503`, and readiness reports the failure; there is no in-process fallback.
- Because `RATE_LIMIT_TRUSTED_PROXIES` is unset, anonymous requests share one
  global bucket. This is conservative: it can rate-limit legitimate anonymous
  traffic sooner, but it cannot be bypassed by spoofing `X-Forwarded-For`.

## Clerk development instance

- Backend uses `CLERK_SECRET_KEY=sk_test_…`; frontend uses the matching
  `VITE_CLERK_PUBLISHABLE_KEY=pk_test_…`.
- The demo profile accepts a development key only when
  `DEPLOYMENT_PROFILE=college-demo`. Live keys are still accepted.
- Clerk Frontend API: `https://social-ferret-6540.clerk.accounts.dev`.
- The development instance reported no explicit allowed-origin restriction
  (`allowed_origins` is unset), so the Railway domain is expected to work. If
  sign-in is rejected, add
  `https://helpdesk-web-production-d96f8e2b.up.railway.app` to the instance's
  allowed origins / redirect URLs before retrying.
- The frontend CSP and the backend `FRONTEND_URL` / Clerk `azp` check must both
  use the same web origin. The backend now normalizes a trailing slash (and a
  redundant default port) in `FRONTEND_URL`/`CORS_ORIGINS` before using them for
  CORS and the `azp` check, so `https://host/` and `https://host` are treated
  identically. A genuinely different host still fails both checks.

## Attachment kill-switch

Attachments are disabled at three layers:

1. **Edge ASGI middleware** (`AttachmentsDisabledMiddleware`) rejects
   `POST /api/v1/tickets/{id}/attachments` with `503` before multipart data is
   parsed or written to disk.
2. **Endpoint guard** re-checks `settings.ATTACHMENTS_ENABLED` as defense in
   depth.
3. **Frontend build flag** `VITE_ATTACHMENTS_ENABLED=false` hides the upload
   control and explains why it is unavailable. The backend remains
   authoritative.

Listing and downloading existing attachment metadata still works. No file is
ever accepted unscanned in this profile.

## Content Security Policy

The web image emits the CSP from `frontend/nginx.conf.template`. It is
deliberately strict: `default-src 'self'`, no `unsafe-eval`, and no wildcard for
the API. Clerk needs specific origins:

- `script-src`: the Clerk Frontend API origin, `challenges.cloudflare.com`, and
  `*.protect.clerk.com`;
- `connect-src`: the API origin, the Frontend API origin, `api.clerk.com`,
  `*.protect.clerk.com`, and Clerk telemetry;
- `frame-src`: the Frontend API origin, `challenges.cloudflare.com`, and
  `*.protect.clerk.com`, because Clerk's bot-protection challenge is framed.

Two real defects were found and fixed while testing the image:

1. `docker-entrypoint.sh` assigned a default to `CLERK_FAPI_ORIGIN` but did not
   export it. `envsubst` only sees exported variables, so the CSP contained two
   spaces instead of the Clerk origin. The entrypoint now exports the value.
2. The template did not allow Clerk's telemetry wildcard or the
   `*.protect.clerk.com` frame origin. Those entries are now present.

Verification: the rebuilt image emits the API origin and the Clerk Frontend API
origin in `script-src`, `connect-src`, and `frame-src`, both when
`CLERK_FAPI_ORIGIN` is supplied and when the entrypoint default is used.

## GitHub automatic deploys

- Railway watches `mdjayedgazi/HelpDesk`.
- `helpdesk-api` deploys on `backend/**` changes; `helpdesk-web` deploys on
  `frontend/**` changes.
- Both watch `main`. Changes were developed on
  `deploy/railway-college-demo` and opened as PR #18, because direct pushes to
  `main` require approval.
- Once PR #18 is merged, Railway builds and deploys both services from `main`
  automatically.
- A `VITE_*` change only takes effect after the frontend service rebuilds.

## Docker

Both services build their existing Dockerfiles.

```bash
# Backend
docker build -t helpdesk-api:college-demo backend

# Frontend (VITE_* are build args)
docker build \
  --build-arg VITE_API_URL=https://helpdesk-api-production-1dc9dd39.up.railway.app \
  --build-arg VITE_CLERK_PUBLISHABLE_KEY="$VITE_CLERK_PUBLISHABLE_KEY" \
  --build-arg VITE_ATTACHMENTS_ENABLED=false \
  -t helpdesk-web:college-demo frontend
```

Local smoke results are recorded in `data.md`. The backend image builds and
starts as uid `10001`; the frontend image serves `/healthz`, the SPA shell and
fallback, a `404` for missing assets, and a CSP containing both the API and
Clerk Frontend API origins. Only the public `VITE_*` values are build
arguments; no server-side secret is passed to the frontend build.

## Migrations

- The schema is owned by Alembic; `AUTO_CREATE_TABLES=false`.
- Neon was already at head (`0009_attachment_scan_status`), so no pre-deploy
  command was configured and no migration ran.
- If a future change adds a migration:

  ```bash
  # One-off, with the same DATABASE_URL (or MIGRATION_DATABASE_URL)
  alembic upgrade head
  ```

  Prefer a Neon direct (non-pooled) endpoint via `MIGRATION_DATABASE_URL` for
  DDL. Take a Neon branch/backup first. Never use `AUTO_CREATE_TABLES=true` in
  production, and never downgrade `0001` on real data.

## Verification

Run against the public URLs after each deployment. Until both services return
`2xx`, they are **not** verified, regardless of the Railway dashboard state.

```bash
API=https://helpdesk-api-production-1dc9dd39.up.railway.app
WEB=https://helpdesk-web-production-d96f8e2b.up.railway.app

curl -fsS "$API/health/live"
curl -fsS "$API/health/ready"

# Production docs must be absent
test "$(curl -sS -o /dev/null -w '%{http_code}' "$API/docs")" = 404
test "$(curl -sS -o /dev/null -w '%{http_code}' "$API/openapi.json")" = 404

# Web shell and SPA fallback; a missing asset must not fall back to index.html
test "$(curl -sS -o /dev/null -w '%{http_code}' "$WEB/")" = 200
test "$(curl -sS -o /dev/null -w '%{http_code}' "$WEB/tickets")" = 200
test "$(curl -sS -o /dev/null -w '%{http_code}' "$WEB/assets/missing.js")" = 404

# The CSP must name the API and Clerk FAPI origins, and must not contain
# empty substitutions (double spaces where an origin should be).
curl -sS -D - -o /dev/null "$WEB/" | grep -i '^content-security-policy'
curl -sS -D - -o /dev/null "$WEB/" | grep -i '^content-security-policy' |
  grep -F 'https://helpdesk-api-production-1dc9dd39.up.railway.app'
curl -sS -D - -o /dev/null "$WEB/" | grep -i '^content-security-policy' |
  grep -F 'https://social-ferret-6540.clerk.accounts.dev'

# API security headers
curl -sS -D - -o /dev/null "$API/health/live" |
  grep -Ei '^(HTTP/|x-content-type-options|x-frame-options|referrer-policy|permissions-policy|content-security-policy|x-request-id):'

# Attachment kill-switch (401/403 is also acceptable before auth; not 2xx)
curl -sS -o /dev/null -w '%{http_code}\n' -X POST \
  "$API/api/v1/tickets/00000000-0000-0000-0000-000000000000/attachments"
```

Also complete in a browser:

1. Sign in through Clerk on the web domain, then reload and confirm the session
   survives.
2. Create a ticket, view it, comment, and confirm persistence after reload.
3. Confirm the upload control is hidden and the demo explanation is shown.
4. Trigger a rate-limited write and confirm `429` with `Retry-After`.
5. Let the API sleep, then confirm the first request recovers (a single `502`
   during cold start is a retry, not a success).
6. In DevTools, confirm API calls go to
   `https://helpdesk-api-production-1dc9dd39.up.railway.app`; the only
   `http://localhost` strings in the bundle are library fallbacks, not requests.
7. Confirm there are no CSP violations in the browser console.

The observed results for this deployment are recorded in `data.md`.

## Limitations

- **Not commercial production.** Clerk runs in development mode, so Clerk
  branding/quotas and development-instance limits apply. Sessions are real, but
  this is a demo identity provider.
- **No attachments.** Deliberate: no ClamAV, no Railway volume, no object
  store. Enabling uploads requires the standard profile and a scanner.
- **Cold starts.** Both services sleep on the Free plan. The first request after
  idle can take several seconds and may surface a Railway `502` before the
  container is awake; retry once. `/health/ready` tolerates up to 10 s per
  dependency probe, but Railway edge timeouts can still affect the very first
  page load. This is a demo trade-off, not a production SLA.
- **Single replica, no HA.** No horizontal scaling, no rollout canary, no
  zero-downtime guarantee.
- **Anonymous rate limiting is coarse.** The shared `anonymous:global` bucket
  is conservative because the Railway proxy range was not verified.
- **HSTS is off on the frontend.** It is enabled only after HTTPS verification;
  this deployment currently serves HTTPS through the Railway domain and can
  turn it on once verified.
- **No automated backups/monitoring configured here.** Neon retains its own
  plan-level history; Railway alerts and spend controls are not configured.
- **Demo data is real data.** Do not enter sensitive information. The database
  is the same Neon project used for development unless a separate branch is
  created.

## Upgrade path

To move from this demo to the commercial profile in `DEPLOYMENT.md`:

1. Switch Clerk to a production instance (`sk_live_`/`pk_live_`) and configure
   the final domain.
2. Set `DEPLOYMENT_PROFILE=standard` (or remove it).
3. Deploy a private ClamAV service, attach a persistent volume for uploads, set
   `UPLOAD_DIR`, `MALWARE_SCAN_ENABLED=true`, and `CLAMAV_*`.
4. Set `ATTACHMENTS_ENABLED=true` and `VITE_ATTACHMENTS_ENABLED=true`, then
   rebuild the frontend.
5. Set the verified `RATE_LIMIT_TRUSTED_PROXIES` CIDRs (or move to a platform
   that supplies a trusted client-IP header) and remove the coarse anonymous
   bucket.
6. Add custom domains, verify TLS, then enable HSTS on both services.
7. Configure backups/PITR, alerts, log retention, and a spend limit.
8. Raise DB pool sizes only after confirming the database connection budget,
   and keep one API replica until uploads move to shared/object storage.

## Rollback

- **Application:** redeploy the previous known-good Railway deployment for the
  affected service. The API is stateless; the frontend is a static image.
- **Configuration:** unset or restore the changed variable and redeploy. A bad
  `VITE_*` value requires a frontend rebuild.
- **Database:** do not downgrade `0001`. Prefer a forward fix and an application
  rollback. Neon branches/history are the recovery path for data.
- **Attachments:** if uploads were ever enabled and must be turned off again,
  set `ATTACHMENTS_ENABLED=false` and rebuild the frontend with
  `VITE_ATTACHMENTS_ENABLED=false`. Existing files are not deleted.
