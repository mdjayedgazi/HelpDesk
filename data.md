# HelpDesk — college-demo deployment review

**Review date:** 2026-11-17
**Repository:** `mdjayedgazi/HelpDesk`
**PR:** [#18 — Deploy: safe Railway college-demo profile](https://github.com/mdjayedgazi/HelpDesk/pull/18)
**PR branch:** `deploy/railway-college-demo`
**Deployment branch:** `main`
**Current PR head at review start:** `e037831` (plus the frontend CSP fixes described below)
**Target:** public college demo on Railway's Free plan, using Railway-generated
HTTPS domains

**Status legend**

| Status | Meaning |
| --- | --- |
| **PASS** | Executed and observed |
| **FAIL** | Executed and failed |
| **NOT VERIFIED** | Not executed, blocked, or requires a live deployment |
| **EXTERNAL** | Managed outside this repository and not changed by this review |

**Bottom line:** the code, local Docker images, database schema, and frontend
build are verified. The public deployment is **not yet verified end to end**.
The API has no active deployment and the live web service still serves a stale
build with a broken CSP. Both are expected to be replaced by a deploy from
`main` after PR #18 merges and `RATE_LIMIT_REDIS_URL` is configured. No
deployment success is claimed here.

---

## 1. Scope and constraints

The review was constrained to the following, and every change respects them:

- Preserve the existing architecture, the Neon database, the Clerk integration,
  the previous security fix `e037831`, and all existing data.
- Exactly two Railway services: `helpdesk-web` and `helpdesk-api`. No Railway
  Postgres, Redis, ClamAV, or volume for the demo.
- No paid infrastructure and no billing changes. Railway Free plan only.
- Attachments stay disabled (`ATTACHMENTS_ENABLED=false`); the API must never
  accept an unscanned file.
- Authentication, authorization, CORS, HTTPS, security headers, and rate
  limiting stay enabled.
- Railway deploys only from `main`. The PR branch was never pushed to `main`,
  the PR was never merged by the agent, and no force-push was used.
- No secret is printed, committed, documented, or used as a command-line
  argument.
- Local Docker was reviewed and smoke-tested.
- The public demo must work on Railway-generated HTTPS domains for college
  users.

---

## 2. Architecture

```text
Browser
  │  HTTPS
  ├──────────────► helpdesk-web (Railway, Nginx, :8080)
  │                  • Vite/React SPA
  │                  • /healthz
  │                  • strict CSP: API + Clerk origins only
  │
  └──────────────► helpdesk-api (Railway, Uvicorn/FastAPI, :8000)
                     • Clerk session verification
                     • async SQLModel/SQLAlchemy + psycopg v3
                     • Redis-backed, fail-closed rate limiting
                     • /health/live, /health/ready
                          │                    │
                          ▼                    ▼
                    Neon PostgreSQL        Upstash Redis
                    pooled endpoint,       rediss:// TLS,
                    sslmode=require        external
```

Key properties:

- The frontend does **not** proxy API traffic. The production bundle calls the
  absolute public API origin directly. CORS and the Nginx `connect-src` both
  allow exactly that origin.
- The API is stateless apart from PostgreSQL and Redis. There is no upload
  volume because attachments are disabled.
- PostgreSQL and Redis are external managed services, so the Railway project
  contains no database, cache, scanner, or attached volume for this demo.

### Repository map

| Area | Path |
| --- | --- |
| API entry point | `backend/app/main.py` |
| Settings and production validation | `backend/app/core/config.py` |
| Database engine and Neon pooler handling | `backend/app/core/database.py` |
| Liveness/readiness | `backend/app/core/health.py` |
| Rate limiting | `backend/app/core/rate_limit.py` |
| Security/body/attachment middleware | `backend/app/core/middleware.py` |
| Clerk verification | `backend/app/core/auth.py` |
| API routers | `backend/app/api/routers/` |
| Migrations | `backend/migrations/` |
| API image | `backend/Dockerfile` |
| Frontend API client | `frontend/src/lib/api.ts` |
| API-base validation | `frontend/src/lib/apiBase.ts` |
| Feature flags | `frontend/src/lib/features.ts` |
| Web image | `frontend/Dockerfile` |
| Web CSP and static serving | `frontend/nginx.conf.template` |
| Web runtime entrypoint | `frontend/docker-entrypoint.sh` |
| CI | `.github/workflows/ci.yml` |
| College-demo runbook | `docs/RAILWAY_COLLEGE_DEMO.md` |
| Commercial production runbook | `docs/DEPLOYMENT.md` |

---

## 3. Runtime and dependency inventory

### Toolchain

| Tool | Local review environment | Pinned by the project |
| --- | --- | --- |
| Python | 3.14.4 on the host; project virtualenv 3.13.1 | `backend/.python-version`, CI `3.13.1`, image `python:3.13.1-slim-bookworm` |
| uv | 0.11.27 | `ghcr.io/astral-sh/uv:0.11.27` |
| Node.js | 24.22.1 on the host | CI `24.15.0`, image `node:24.15.0-bookworm-slim`; `engines` requires `>=24.15 <25` |
| npm | 12.2.0 | `devEngines` and image pin |

The host Node is newer than the pinned CI/image version but satisfies the
project `engines` range. The Docker build used the pinned 24.15.0 image.

### Backend Python packages

| Package | Version |
| --- | --- |
| FastAPI | 0.162.0 |
| Starlette | 1.8.0 |
| Pydantic | 2.14.1 |
| SQLAlchemy | 2.1.6 |
| SQLModel | 0.0.48 |
| psycopg | 3.3.6 |
| Alembic | 1.20.1 |
| redis | 8.1.0 |
| clerk-backend-api | 7.0.0 |
| dnspython | 2.9.2 |
| OpenTelemetry API/SDK | 1.45.2 |

`uv sync --frozen` completed against the committed lockfile, so the resolved
versions match `uv.lock`.

### Frontend packages

| Package | Version |
| --- | --- |
| React / React DOM | 19.3.1 |
| React Router DOM | 7.18.4 |
| `@clerk/react` | 6.17.8 |
| Chakra UI | 3.37.0 |
| TanStack Query | 5.104.3 |
| TypeScript | 6.0.3 installed (`~6.0.2` range) |
| Vite Plus / Vite core | 1.2.0 (`@voidzero-dev/vite-plus-core@1.2.0`) |
| Tailwind CSS | 4.3.3 |
| npm | 12.2.0 |

---

## 4. Configuration review

No secret values are reproduced here. Only variable names, classification, and
the presence/absence of a value are recorded.

### Backend (`helpdesk-api`) variables

| Variable | Classification | Railway state | Review |
| --- | --- | --- | --- |
| `ENVIRONMENT` | non-secret | `production` | Enables fail-closed validation and disables docs |
| `DEPLOYMENT_PROFILE` | non-secret | `college-demo` | Only profile that accepts `sk_test_` and no scanner |
| `DATABASE_URL` | secret | present | Neon pooled host, `sslmode=require` |
| `CLERK_SECRET_KEY` | secret | present | Clerk development key (`sk_test_`) |
| `FRONTEND_URL` | public | present | Exact Railway web origin |
| `AUTO_CREATE_TABLES` | non-secret | `false` | Schema owned by Alembic |
| `DATABASE_ECHO` | non-secret | `false` | No SQL data in logs |
| `RATE_LIMIT_ENABLED` | non-secret | `true` | Mandatory in production |
| `RATE_LIMIT_REDIS_URL` | secret | **missing** | **Blocker:** API cannot start |
| `ATTACHMENTS_ENABLED` | non-secret | `false` | Upload kill-switch |
| `MALWARE_SCAN_ENABLED` | non-secret | `false` | Allowed only because attachments are off |
| `DB_POOL_SIZE` | non-secret | `1` | Fits 0.5 GB service and Neon limits |
| `DB_MAX_OVERFLOW` | non-secret | `0` | No burst connections |
| `LOG_LEVEL` | non-secret | `INFO` | |
| `LOG_JSON` | non-secret | `true` | Structured, redacted logs |
| `HSTS_ENABLED` | non-secret | `false` | Enable only after HTTPS verification |

Deliberately unset: `RATE_LIMIT_TRUSTED_PROXIES`, `CORS_ORIGINS`, `UPLOAD_DIR`,
`CLAMAV_HOST`, `CLAMAV_PORT`, `MIGRATION_DATABASE_URL`,
`CLERK_WEBHOOK_SECRET`, `CLERK_JWKS_URL`, `DB_STATEMENT_TIMEOUT_MS`.

`RATE_LIMIT_TRUSTED_PROXIES` is unset because Railway edge CIDRs were not
verified. The limiter therefore ignores `X-Forwarded-For` and gives anonymous
callers one shared `anonymous:global` bucket. Authenticated writes remain keyed
by Clerk user id.

### Frontend (`helpdesk-web`) variables

| Variable | Kind | Railway state | Review |
| --- | --- | --- | --- |
| `VITE_API_URL` | build-time | present | Public API origin |
| `VITE_CLERK_PUBLISHABLE_KEY` | build-time, public | present | Matches the development instance |
| `VITE_ATTACHMENTS_ENABLED` | build-time | `false` | Hides upload UI |
| `API_ORIGIN` | runtime | present | Same origin as `VITE_API_URL` |
| `CLERK_FAPI_ORIGIN` | runtime | present | Exact Clerk Frontend API host |
| `PORT` | runtime | `8080` | Nginx listen/health port |
| `HSTS_ENABLED` | runtime | `false` | Enable only after HTTPS verification |

`VITE_*` values are compiled into the bundle; changing one requires a rebuild.
`API_ORIGIN` and `CLERK_FAPI_ORIGIN` are read by `docker-entrypoint.sh`.

### Secret handling

- `.env` files are git-ignored and Docker-ignored; no `.env` file is tracked.
- No real key was found in tracked files or in the committed docs.
- Railway secrets were streamed over stdin, never passed as command-line
  arguments and never printed.
- `railway variable list` was not used for secret inspection.
- This review records names and presence only. It does not reproduce values.
- The frontend bundle contains only public build-time values. No server secret
  is passed to the frontend build.

---

## 5. Security review

### Authentication and authorization — PASS

- Backend verifies Clerk session tokens with `clerk-backend-api`; it derives the
  user from the verified session rather than from client-supplied identity.
- `FRONTEND_URL` is used both for CORS and for the Clerk token authorized-party
  (`azp`) check, so a token minted for another origin is rejected.
- Role checks are enforced by API dependencies. The public demo does not add a
  bypass, an anonymous admin path, or a demo-only authorization relaxation.
- The Owner bootstrap command is not part of the request path and was not run.

### CORS — PASS

- Allowed origins are exactly `FRONTEND_URL` (plus explicit `CORS_ORIGINS`,
  which is unset). No wildcard.
- Credentials are allowed only for those exact origins.
- Allowed methods and headers are enumerated; rate-limit and request-id headers
  are exposed so browsers can read them.

### HTTPS and transport — PASS (platform-enforced)

- Railway terminates TLS on `*.up.railway.app`; the API and web domains are
  HTTPS-only service domains.
- `FRONTEND_URL` and `VITE_API_URL` production validation reject non-HTTPS and
  localhost origins.
- HSTS is intentionally off until the final domain and TLS chain are verified.
  This is documented; it is not a silent omission.

### Security headers — PASS locally, FAIL on the stale live web build

- API responses include `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, a restrictive `Referrer-Policy`,
  `Permissions-Policy`, a `default-src 'none'` CSP, and a request id.
- Web responses include `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Permissions-Policy`, COOP/CORP, cache control, and the
  Clerk-compatible CSP.
- **Stale live web build:** the public web CSP contains empty substitutions
  where the Clerk Frontend API origin should be, e.g.
  `script-src 'self'  https://challenges.cloudflare.com`. Clerk JavaScript is
  therefore blocked. This is the reason the two frontend fixes below exist.

### Content Security Policy — PASS after the fix

The rebuilt image emits a CSP containing:

- `script-src`: `'self'`, the Clerk Frontend API origin, Cloudflare challenges,
  and `*.protect.clerk.com`;
- `connect-src`: `'self'`, the API origin, the Clerk Frontend API origin,
  `api.clerk.com`, `*.protect.clerk.com`, and Clerk telemetry;
- `frame-src`: `'self'`, the Clerk Frontend API origin, Cloudflare challenges,
  and `*.protect.clerk.com`;
- no `unsafe-eval` and no wildcard for the API or the whole web.

### Rate limiting — PASS by configuration and tests; live Redis NOT VERIFIED

- Production requires `RATE_LIMIT_ENABLED=true` and a valid Redis URL.
- The API pings Redis during startup and fails startup if it is unreachable.
- Protected writes fail closed with `503` when the store is unavailable.
- Budgets are per user for authenticated writes. Anonymous demo callers share a
  single conservative bucket because trusted proxy ranges are unset.
- `429` responses include `Retry-After`; headers expose limit/remaining/reset.
- **Live blocker:** no `RATE_LIMIT_REDIS_URL` is configured yet, so the API
  cannot start. Local tests use a disposable/stubbed store; live Redis behavior
  is not verified.

### Attachments — PASS (disabled)

Attachments are disabled at three independent layers:

1. `AttachmentsDisabledMiddleware` rejects
   `POST /api/v1/tickets/{id}/attachments` with `503` before multipart parsing
   or disk writes.
2. The endpoint re-checks `settings.ATTACHMENTS_ENABLED`.
3. `VITE_ATTACHMENTS_ENABLED=false` hides upload controls and explains why.

Listing and downloading existing attachment metadata still works. No file is
accepted unscanned in this profile. Local smoke test returned `503` for an
upload attempt.

### Database access — PASS

- All access goes through SQLModel/SQLAlchemy parameterized queries; no raw
  string interpolation of user input was found in the reviewed data paths.
- Neon's pooled endpoint is detected (`-pooler` hostname) and psycopg prepared
  statements are disabled (`prepare_threshold=None`) to avoid PgBouncer
  transaction-mode collisions.
- Runtime pool is `1` connection with `0` overflow. This is deliberate for the
  Free plan and Neon connection limits.
- `AUTO_CREATE_TABLES=false`; schema changes require Alembic.

### Logging and error handling — PASS

- Production JSON logging redacts authorization headers, Clerk keys,
  credential-bearing database/Redis URLs, and common secret fields.
- Request bodies and authorization headers are not logged.
- Readiness returns coarse statuses and does not echo hosts, ports,
  credentials, or exception text.
- Production docs/OpenAPI routes are disabled.

### Dependency posture — PASS with documented dev-only advisories

- `pip-audit`: no known Python vulnerabilities.
- `npm audit --omit=dev`: 0 vulnerabilities.
- Full `npm audit`: 5 moderate advisories in the **development** test toolchain
  (`vitest` / `@vitest/ui` / `@vitest/browser-preview`, GHSA-p458-7748-mcp3).
  The suggested fix upgrades `vite-plus` from 1.2.0 to 1.7.0, outside the
  current range and coupled to the Vite core override. That larger upgrade was
  not forced into a deployment PR; the advisories affect local test tooling,
  not the production bundle.

---

## 6. Changes made in this pass

### 6.1 Fixed: Clerk Frontend API origin was dropped from the CSP

**File:** `frontend/docker-entrypoint.sh`

The entrypoint assigned a shell default to `CLERK_FAPI_ORIGIN` but did not
export it. `envsubst` substitutes only exported variables, so when Railway left
the variable unset the Nginx template received an empty value. The CSP then
contained double spaces and no Clerk origin, which blocked Clerk JavaScript.

The entrypoint now exports `CLERK_FAPI_ORIGIN` after applying the default and
before `envsubst`. The existing scheme/character validation still runs.

### 6.2 Fixed: incomplete Clerk origins in the CSP

**File:** `frontend/nginx.conf.template`

- Added `https://*.clerk-telemetry.com` to `connect-src` so Clerk telemetry does
  not violate the policy.
- Added `https://*.protect.clerk.com` to `frame-src` so Clerk's bot-protection
  challenge can be framed.
- Kept the Clerk Frontend API origin in `script-src`, `connect-src`, and
  `frame-src`.
- Kept `'self'` in `frame-src` for the application's own framing needs.

No CSP wildcard was added for the API, and `unsafe-eval` was not introduced.

### 6.3 Documentation

- `docs/RAILWAY_COLLEGE_DEMO.md`: corrected the API healthcheck to
  `/health/live`, documented the `/health/ready` monitoring split, corrected
  the Free-plan credit, recorded the pre-merge live status, documented the CSP
  fix, the Clerk FAPI variable, the missing Redis variable, Upstash setup,
  post-merge verification, and the cold-start `502` behavior.
- `README.md`: linked the college-demo runbook and distinguished it from the
  commercial production profile.
- `docs/DEPLOYMENT.md`: cross-linked the demo profile and removed the stale
  claim that no commit/deployment had ever been made.
- `data.md`: this review.

No backend application code, database migration, schema, Clerk configuration,
Neon data, or Railway service topology was changed in this pass.

---

## 7. Verification evidence

### 7.1 Backend quality gates — PASS

| Check | Command | Result |
| --- | --- | --- |
| Locked dependency sync | `uv sync --frozen --group dev` | PASS — 80 packages checked |
| Lint | `uv run ruff check .` | PASS — all checks passed |
| Format | `uv run ruff format --check .` | PASS — 103 files already formatted |
| Tests | `uv run pytest -q` | PASS — **404 passed, 45 skipped** in 19.66 s |
| Dependency audit | `uvx pip-audit` | PASS — no known vulnerabilities |

The 45 skips are the PostgreSQL/Redis integration suites that require disposable
services; CI runs those separately.

### 7.2 Frontend quality gates — PASS

| Check | Result |
| --- | --- |
| `npm run typecheck` | PASS |
| `npm run lint` | PASS |
| `npm test` | PASS — 42 tests in 6 files, 622 ms |
| Production build | PASS — 1,228.11 kB JS (341.84 kB gzip), 7.53 kB CSS (2.19 kB gzip) |
| `npm audit --omit=dev --audit-level=high` | PASS — 0 vulnerabilities |
| Full `npm audit` | 5 moderate, development toolchain only (documented above) |

The build used CI-style HTTPS values, not localhost. The bundle contains the
Railway API origin and the Clerk publishable key. The only `http://localhost`
strings found are internal library fallbacks in Clerk/Zod code, not application
requests.

### 7.3 Docker images — PASS

| Image | Result |
| --- | --- |
| `helpdesk-api:college-demo` | Build PASS |
| `helpdesk-web:college-demo` | Build PASS |

The frontend build emits a Docker warning that
`VITE_CLERK_PUBLISHABLE_KEY` is used in `ARG`/`ENV`. That key is public by
design; no secret key is passed to the frontend build.

### 7.4 Backend container smoke — PASS

Run with a disposable SQLite database, `ENVIRONMENT=development`, attachments
disabled, and rate limiting disabled (the production profile would require
PostgreSQL and Redis):

| Check | Result |
| --- | --- |
| `/health/live` | `200` |
| `/health/ready` | `200`, `database: ok`, `redis: disabled`, `clamav: disabled` |
| Main process user | uid `10001` (verified in `/proc/1/status` and `docker top`) |
| Attachment upload | `503` (rejected before parsing) |
| API security headers | Present |
| API CSP | `default-src 'none'; frame-ancestors 'none'; ...` |

### 7.5 Web container smoke — PASS

| Check | Result |
| --- | --- |
| `/healthz` | `200` |
| `/` | `200` |
| `/tickets` (SPA fallback) | `200` |
| `/assets/missing.js` | `404` |
| CSP with explicit `CLERK_FAPI_ORIGIN` | Contains API + exact Clerk host |
| CSP with `CLERK_FAPI_ORIGIN` unset | Contains API + `https://*.clerk.accounts.dev` (export fix verified) |
| CSP with Clerk telemetry/frame entries | Present |
| Bundle API origin | Only the Railway API origin |

### 7.6 Neon PostgreSQL — PASS (read-only)

| Check | Result |
| --- | --- |
| Server version | PostgreSQL 18.7 |
| Alembic current | `0009_attachment_scan_status` (head) |
| `alembic check` | No new upgrade operations detected |
| `users` | 1 |
| `tickets` | 0 |
| `comments` | 0 |
| `attachments` | 0 |
| Other workflow tables | 0 rows |

No migration was run. No data was inserted, updated, or deleted. The runtime URL
is a Neon pooled host with `sslmode=require`.

### 7.7 Clerk — PASS for configuration, live sign-in NOT VERIFIED

- Development instance (`environment_type=development`).
- Frontend API host: `https://social-ferret-6540.clerk.accounts.dev`.
- The publishable key decodes to that host.
- The instance reported no explicit allowed-origin restriction
  (`allowed_origins` unset), so the Railway web origin is expected to be
  accepted.
- Backend uses the matching development secret; the frontend uses the matching
  publishable key.
- Live sign-up/sign-in cannot be verified until the web service is redeployed
  with the fixed CSP and the API is deployed.

### 7.8 Railway project state — EXTERNAL, partially verified

| Item | State |
| --- | --- |
| Project | `helpdesk-college-demo`, environment `production`, region `ams` |
| Services | Exactly `helpdesk-web` and `helpdesk-api` |
| Railway Postgres/Redis/ClamAV | None |
| Attached volumes | None |
| Detached volume | Pre-existing `redis-volume` (unrelated, untouched) |
| Web domain | `https://helpdesk-web-production-d96f8e2b.up.railway.app` |
| API domain | `https://helpdesk-api-production-1dc9dd39.up.railway.app` |
| Web source | root `/frontend`, `Dockerfile`, watch `frontend/**` |
| API source | root `/backend`, `Dockerfile`, watch `backend/**` |
| Web healthcheck | `/healthz`, timeout 300 s |
| API healthcheck | `/health/live`, timeout 300 s |
| Replicas | 1 each |
| Sleep when idle | Enabled for both |
| Auto deploy | `main` only, both services, `checkSuites=true` (Wait for CI) |

### 7.9 Live public endpoints — FAIL / NOT VERIFIED

| Check | Observed | Status |
| --- | --- | --- |
| Web `/` | `200` but stale build | **FAIL for auth** |
| Web CSP | Empty Clerk substitutions | **FAIL** |
| Web sign-in | Clerk JS blocked by CSP | **FAIL** |
| API `/health/live` | `404 "Application not found"` | **FAIL** |
| API `/health/ready` | Not reachable | **NOT VERIFIED** |
| API docs `/docs` | Not reachable | **NOT VERIFIED** |
| Attachment kill-switch on live API | Not reachable | **NOT VERIFIED** |
| End-to-end ticket creation | Not possible | **NOT VERIFIED** |
| Rate limiting on live API | Not possible | **NOT VERIFIED** |
| Cold start/wake | Not tested on a working API | **NOT VERIFIED** |

The live API failure is the old Railpack build from the repository root, not a
failure of the current Dockerfile configuration. No successful API deployment
exists yet.

---

## 8. Blockers before the public demo is usable

1. **Set `RATE_LIMIT_REDIS_URL` on `helpdesk-api`.**
   Production validation rejects the empty value, and the FastAPI lifespan
   pings Redis before serving traffic. Use an Upstash `rediss://` URL and stream
   it over stdin; do not paste it into a shell argument or this document.
2. **Merge PR #18 with the frontend CSP fixes.**
   Railway only deploys `main`. The current live web build predates the fix.
3. **Verify the deploy from `main`.**
   Both services must build with their Dockerfiles from `/backend` and
   `/frontend`. The API must serve `/health/live` and `/health/ready` with
   `200`; the web CSP must name both origins.
4. **Run the browser smoke test.**
   Clerk sign-in, ticket creation, comment, persistence, attachments hidden,
   rate-limit `429`, and cold-start retry.

The PR was intentionally left open for user approval. The agent did not merge
it and did not push to `main`.

---

## 9. Limitations of this profile

- **Not commercial production.** Clerk runs a development instance; branding,
  quotas, and development-instance behavior apply. Sessions are real, but this
  is a demo identity provider.
- **No attachments.** No ClamAV, no volume, no object store. Enabling uploads
  requires the standard profile and a working scanner.
- **Free-plan cold starts.** Both services sleep. The first request after idle
  can be slow and may return a Railway `502`; retry once.
- **Single replica, no HA.** No horizontal scaling, rollout canary, or
  zero-downtime guarantee.
- **Coarse anonymous rate limiting.** The shared `anonymous:global` bucket can
  limit legitimate anonymous traffic sooner because Railway proxy ranges are
  not trusted. Authenticated limits remain per user.
- **HSTS off.** The Railway HTTPS domain works, but HSTS is enabled only after
  the final domain/TLS chain is verified.
- **No backups, monitoring, or spend alerts configured here.** Neon retains its
  own plan-level history; Railway alerts and spend controls are not configured.
- **Demo data is real data.** The demo uses the existing Neon database. Do not
  enter sensitive information.
- **Large frontend bundle.** About 1.23 MB JS / 342 kB gzip. It works; code
  splitting is a future performance task.
- **Dev-only npm advisories.** Five moderate advisories remain in the Vitest
  toolchain; the fix requires a larger Vite Plus upgrade. Production dependencies
  are clean.

---

## 10. Upgrade path to the commercial profile

To move from this demo to the standard profile in `docs/DEPLOYMENT.md`:

1. Switch Clerk to a production instance (`sk_live_` / `pk_live_`) and configure
   the final domain and allowed origins.
2. Set `DEPLOYMENT_PROFILE=standard` (or remove it).
3. Deploy a private ClamAV service, attach a persistent volume, set
   `UPLOAD_DIR`, `MALWARE_SCAN_ENABLED=true`, and `CLAMAV_*`.
4. Set `ATTACHMENTS_ENABLED=true` and `VITE_ATTACHMENTS_ENABLED=true`, then
   rebuild the frontend.
5. Set verified `RATE_LIMIT_TRUSTED_PROXIES` CIDRs and remove the coarse
   anonymous bucket. Keep authenticated per-user limits.
6. Add custom domains, verify TLS, then enable HSTS on both services.
7. Configure backups/PITR, alerts, log retention, and a spend limit.
8. Raise DB pool sizes only after confirming the Neon connection budget. Keep
   one API replica until uploads move to shared/object storage.

---

## 11. Post-merge verification checklist

Do not mark the deployment successful until every applicable item is observed.

- [ ] PR #18 merged into `main` by the user.
- [ ] Railway deployed `helpdesk-api` from `main` with root `/backend` and
      `backend/Dockerfile`.
- [ ] Railway deployed `helpdesk-web` from `main` with root `/frontend` and
      `frontend/Dockerfile`.
- [ ] API deployment status `SUCCESS`; no crash loop.
- [ ] `GET /health/live` returns `200`.
- [ ] `GET /health/ready` returns `200` with database and Redis `ok`.
- [ ] `/docs`, `/redoc`, `/openapi.json` return `404`.
- [ ] Web `/` and a deep link return `200`; a missing asset returns `404`.
- [ ] Web CSP contains the exact API origin and Clerk Frontend API origin, with
      no empty substitutions.
- [ ] Browser console has no CSP violations.
- [ ] Clerk sign-up/sign-in succeeds; session survives reload.
- [ ] Ticket creation, viewing, comment, and persistence work.
- [ ] Attachment control is hidden; direct upload returns `503`.
- [ ] A rate-limited write returns `429` with `Retry-After`.
- [ ] API cold start recovers on retry; no permanent `502`.
- [ ] Browser API calls go to the Railway API origin, not localhost.
- [ ] Neon row counts increase only with intentional demo activity.
- [ ] No secret appears in logs, browser output, screenshots, or this document.

---

## 12. Rollback

- **Application:** redeploy the previous known-good Railway deployment for the
  affected service. The API is stateless; the frontend is a static image.
- **Configuration:** restore or unset the changed variable and redeploy. A bad
  `VITE_*` value requires a frontend rebuild.
- **Database:** do not downgrade `0001`. Prefer a forward fix and an application
  rollback. Neon branches/history are the recovery path.
- **Attachments:** if uploads were ever enabled and must be disabled again, set
  `ATTACHMENTS_ENABLED=false` and rebuild with
  `VITE_ATTACHMENTS_ENABLED=false`. Existing files are not deleted.

---

## 13. Conclusion

The repository is ready to merge and deploy as a **college demo**, subject to
the two external actions: configure Upstash Redis and merge the PR. The code
changes are limited and reviewed; the standard production profile remains
strict; the Neon database is unchanged at head; and local Docker proves the
fixed CSP and attachment kill-switch behavior.

The public deployment is **not yet verified**. The API is not running and the
live web build is stale. A successful deployment must be demonstrated from
`main` after merge, not inferred from local results or the Railway dashboard.
