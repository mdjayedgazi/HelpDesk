# HelpDesk production-readiness remediation review

**Review date:** 2026-10-29
**Repository:** `/home/jayed/Projects/HelpDesk`
**Branch:** `oddit`
**HEAD:** `e85345bc26a81e33febedf0491b67bcfb321b74c` (same commit as `main`)
**Working tree:** uncommitted; 31 modified tracked files and 17 untracked paths
after this report was written. No commit, push, merge, or deployment was created.
**Verdict:** **CONDITIONAL GO** for a controlled staging/production rollout after
the external Railway and provider checks in §9 are completed. **NO-GO for public
production traffic** until those checks, the authorized commit, and the final
smoke tests are done.

This file is the authoritative remediation record. `PROJECT_CONTEXT.md` remains
the architecture/onboarding document; `docs/DEPLOYMENT.md` is the operational
Railway runbook.

---

## 1. Status legend

| Status | Meaning in this review |
| --- | --- |
| `FIXED AND VERIFIED` | The change is implemented and covered by a passing local test or a directly observed local deployment smoke check. |
| `FIXED, EXTERNAL VERIFICATION PENDING` | The code/test evidence passes locally, but the real provider, account, domain, scanner, or hosted CI has not been verified. |
| `OPEN` | A known item remains; it is not claimed as complete. |
| `ACCEPTED RISK` | A documented residual risk is knowingly retained. |
| `NOT VERIFIED` | No direct evidence exists; absence of a failure is not treated as a pass. |
| `NOT APPLICABLE` | The item does not require a code change or is intentionally out of scope. |

Severity labels are `Critical`, `High`, `Medium`, `Low`, and `Info`.

---

## 2. Executive summary

The remediation closes the confirmed code-level defects in the reviewed scope:

- the critical `certifi` advisory is removed and the production dependency audit
  is clean;
- production startup is fail-closed for placeholders, insecure origins,
  localhost dependencies, disabled limits/scanning, temporary upload storage,
  missing trusted proxies, and invalid pool/limit/timeout values;
- request sizes are bounded before JSON/multipart parsing or spooling, uploads
  have per-file and per-ticket quotas, and API responses carry security and
  no-store headers;
- `/docs`, `/redoc`, and `/openapi.json` are disabled in production;
- explicit-null updates, whitespace-only input, integrity-error mapping,
  concurrent ticket updates, status timestamps, database timeouts, and the
  Owner-conversation N+1/unbounded read are fixed;
- the frontend enforces a production HTTPS `VITE_API_URL`, the Nginx image has
  SPA fallback/caching/CSP, and both images are deployable;
- CI has production dependency-audit checks and a frontend build environment;
- the Railway runbook covers volume persistence, ClamAV, migrations, health
  checks, TLS/HSTS, backups, monitoring, and rollback.

What is **not** proven: Railway service provisioning, custom domains/TLS,
hosted CI execution, a live ClamAV daemon and legacy-file rescan, a live shared
Redis deployment, production Clerk sign-in/CORS, PostgreSQL backup/PITR restore,
monitoring, and a browser end-to-end/a11y run. These are explicitly listed as
`NOT VERIFIED` or `FIXED, EXTERNAL VERIFICATION PENDING` below.

---

## 3. Repository state and preserved work

| Item | Evidence |
| --- | --- |
| Branch / HEAD | `git branch --show-current` → `oddit`; `git rev-parse HEAD` → `e85345b`; `git branch -vv` → same commit as `main`. |
| No commit created | `git status` shows uncommitted changes; no commit/push/merge/deploy command was run. |
| Pre-existing user changes | `backend/pyproject.toml` and `backend/uv.lock` were preserved. The lockfile now also contains the reviewed `certifi` upgrade. |
| Disposable services only | PostgreSQL `postgres:18-alpine` on `127.0.0.1:55432` and Redis `redis:7-alpine` on `127.0.0.1:56379`; no persistent or production database was touched. |
| Secrets | No real secret, token, credential-bearing URL, or production value was printed or committed. Test values used only inside disposable containers. |

### Modified tracked files

```text
.github/workflows/ci.yml
backend/.env.example
backend/README.md
backend/app/api/routers/attachments.py
backend/app/api/routers/notifications.py
backend/app/api/routers/staff_messages.py
backend/app/api/routers/tickets.py
backend/app/api/routers/users.py
backend/app/core/config.py
backend/app/core/database.py
backend/app/core/rate_limit.py
backend/app/main.py
backend/app/schemas/comments.py
backend/app/schemas/ticket_feedback.py
backend/app/schemas/tickets.py
backend/app/schemas/users.py
backend/app/services/staff_messages.py
backend/pyproject.toml
backend/tests/conftest.py
backend/tests/test_attachments.py
backend/tests/test_postgres_integration.py
backend/tests/test_rate_limit.py
backend/tests/test_staff_messages.py
backend/uv.lock
frontend/index.html
frontend/package-lock.json
frontend/package.json
frontend/src/lib/api.ts
frontend/vite.config.ts
PROJECT_CONTEXT.md
data.md
```

### Untracked files added by this pass

```text
backend/.dockerignore
backend/Dockerfile
backend/app/core/health.py
backend/app/core/logging.py
backend/app/core/middleware.py
backend/docker-entrypoint.sh
backend/tests/test_production_hardening.py
docs/DEPLOYMENT.md
frontend/.dockerignore
frontend/.env.example
frontend/.nvmrc
frontend/Dockerfile
frontend/docker-entrypoint.sh
frontend/nginx.conf.template
frontend/public/theme-init.js
frontend/src/lib/apiBase.test.ts
frontend/src/lib/apiBase.ts
```

---

## 4. Method and evidence boundary

The review used source inspection plus executed commands:

- backend unit/API tests against in-memory SQLite, with Clerk stubbed;
- opt-in PostgreSQL integration tests against a disposable container;
- opt-in Redis limiter tests against a disposable container;
- Alembic upgrade/downgrade/re-upgrade and `alembic check` on the disposable
  PostgreSQL database;
- production-mode Uvicorn and Docker container smoke tests;
- frontend typecheck, lint, unit tests, production build, and Nginx container
  smoke tests;
- `pip-audit`, `npm audit`, and `actionlint`.

It did **not** have Railway account access, a real ClamAV service, production
Clerk credentials, production data, DNS control, or hosted CI results. Claims
that require those are marked accordingly; they are not inferred as passes.

---

## 5. Findings and status

### 5.1 Previously tracked findings

| ID | Severity | Finding | Status | Evidence / residual note |
| --- | --- | --- | --- | --- |
| F-01 | Medium | `data.md` was empty but referenced as the audit contract. | `FIXED AND VERIFIED` | This file is now a complete review; assignment behavior remains covered by `backend/tests/test_assignment.py`. |
| F-02 | Low | Customer "Dashboard" nav pointed at the public homepage. | `FIXED AND VERIFIED` | `frontend/src/components/nav.ts` points to `/dashboard`; nav test passes in the 39-test frontend suite. |
| F-03 | Medium | No CI/CD configuration. | `FIXED, EXTERNAL VERIFICATION PENDING` | Workflow has backend lint/tests with Redis, frontend checks/build, PostgreSQL migrations/integration, and dependency audits. `actionlint` is clean. It has not run on GitHub. |
| F-04 | Medium | No frontend automated tests. | `FIXED AND VERIFIED` | 5 test files / 39 tests pass; typecheck, lint, and production build pass. |
| F-05 | Low / operational | Dirty working tree. | `OPEN` | Intentionally preserved. A commit/review is blocked by the no-commit authorization in this task. |
| F-06 | Low | Stray root `package-lock.json` with no root `package.json`. | `OPEN` | Left untouched; deleting it is a repository-ownership decision. Not used by frontend builds. |
| F-07 | Low | Backend lint/format was not clean. | `FIXED AND VERIFIED` | `ruff check` and `ruff format --check` are clean (91 files checked in the final pass). |
| F-08 | Medium | Uploads lacked malware/content inspection. | `FIXED, EXTERNAL VERIFICATION PENDING` | Signature checks, ClamAV INSTREAM, quarantine, `PENDING`/`CLEAN`/`INFECTED`, on-demand rescan, fail-closed scanner errors. No live clamd or legacy backlog rescan was available. |
| F-09 | Medium | No application-level rate limiting. | `FIXED, EXTERNAL VERIFICATION PENDING` | Redis fixed-window limiter, proxy resolution, 429/Retry-After, 503 fail-closed. 14 tests pass against disposable Redis; the deployed shared Redis is not verified. |
| F-10 | Low | `ticket_number` nullable at the model layer. | `FIXED AND VERIFIED` | Model/migration `0008` non-null contract; disposable PostgreSQL upgrade passes. No persistent database was migrated. |
| F-11 | Info | Owner naming/legacy `INITIAL_ADMIN_EMAIL` drift. | `NOT APPLICABLE` | Compatibility name retained and documented; no rename is required for production. |
| F-12 | Info | Historical reports were not reproducible. | `FIXED AND VERIFIED` | This file records commands/results and labels external claims; prior audit history is retained in `PROJECT_CONTEXT.md`. |
| F-13 | Medium | Self-service email could pre-claim another address. | `FIXED AND VERIFIED` | Email is Clerk-authoritative; changed-email PATCHes are rejected, unchanged no-op is preserved, tests cover the pre-claim sequence. |

### 5.2 Production-hardening findings

| ID | Severity | Finding | Status | Evidence / residual note |
| --- | --- | --- | --- | --- |
| H-01 | Critical | `certifi` bundled compromised eMudhra/emSign roots. | `FIXED AND VERIFIED` | GHSA-6q48-6c7w-9gw2 / PYSEC-2026-4320 affects `>=2019.03.09, <2026.10.18`; lock upgraded from `2026.7.22` to `2026.10.23`; production `pip-audit` reports no known vulnerabilities. |
| H-02 | High | Production configuration could start with placeholders/localhost/disabled controls. | `FIXED AND VERIFIED` | `backend/app/core/config.py` validates all required production values and raises `RuntimeError` after parsing, without echoing secrets. 55 hardening tests pass. |
| H-03 | High | No request-body/multipart cap before parsing/spooling. | `FIXED AND VERIFIED` | `BodySizeLimitMiddleware` rejects declared and chunked oversized bodies before FastAPI parsing; tests cover `Content-Length` and chunked multipart `413`. |
| H-04 | High | Missing browser/API security headers and cache policy. | `FIXED AND VERIFIED` | Backend and frontend send CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy`, COOP/CORP, and optional HSTS; API responses send `Cache-Control: no-store`. Observed in Docker smoke tests. |
| H-05 | High | API docs/OpenAPI exposed in production. | `FIXED AND VERIFIED` | Production config disables `/docs`, `/redoc`, `/openapi.json`; container smoke returns `404` for `/docs` and `/openapi.json` (and the routes are unregistered). |
| H-06 | Medium | HSTS could be enabled before HTTPS was verified. | `FIXED AND VERIFIED` | `HSTS_ENABLED` is opt-in on both services and defaults to false; runbook requires verified custom-domain TLS before enabling. Production HSTS itself remains external verification. |
| H-07 | High | Explicit nulls and whitespace-only values caused ambiguous or unsafe updates. | `FIXED AND VERIFIED` | Ticket/profile required-field nulls return `422`; text is trimmed before length validation; ticket/comment/feedback/user/staff/account-request limits are bounded. Regression tests pass. |
| H-08 | High | Concurrent ticket updates and status timestamps were not serialized. | `FIXED AND VERIFIED` | `FOR UPDATE` row loading on update/claim; PostgreSQL concurrency test; `RESOLVED → CLOSED` preserves `resolved_at`, reopening clears it. |
| H-09 | Medium | Database calls could hang indefinitely. | `FIXED AND VERIFIED` | Pool/connect/statement timeouts are configured; a PostgreSQL test confirms `SHOW statement_timeout` receives the psycopg `options` value. |
| H-10 | Medium | Owner conversation list was unbounded and N+1. | `FIXED AND VERIFIED` | Bulk aggregate/latest-message queries and `limit`/`offset`; pagination test and aggregate behavior tests pass. |
| H-11 | Medium | Production frontend could build with a missing/localhost API URL. | `FIXED AND VERIFIED` | `vite.config.ts` and `resolveApiBase` fail the build for missing/non-HTTPS/localhost/path-bearing values; tests cover the cases; empty-env build was observed to fail. |
| H-12 | Medium | Health endpoint did not separate liveness from dependency readiness. | `FIXED AND VERIFIED` | `/health`, `/health/live`, and `/health/ready`; readiness checks PostgreSQL, Redis, and ClamAV; container observed `live=200`, `ready=503` with DB/Redis `ok` and ClamAV intentionally down. |
| H-13 | High | No production container/Railway deployment definition. | `FIXED AND VERIFIED` | Backend/frontend Dockerfiles, non-root backend process, entrypoint volume preparation, Nginx SPA/CSP/caching, `.dockerignore`, `.env.example`, `.nvmrc`. Both images built and smoke-tested locally. |
| H-14 | Medium | CI had no dependency-audit gate. | `FIXED, EXTERNAL VERIFICATION PENDING` | CI audits production Python and frontend dependencies. Local `pip-audit`/`npm audit` pass; hosted CI has not run. |
| H-15 | Medium | Logs could leak credentials and were not structured. | `FIXED AND VERIFIED` | JSON/human formatters redact bearer tokens, Clerk keys, credential-bearing database/Redis URLs, and password/secret fields; redaction test passes. |
| H-16 | Medium | Legacy `PENDING` attachments had no recovery path. | `FIXED, EXTERNAL VERIFICATION PENDING` | On-demand rescan before download and a one-off rescan command; scanner failures fail closed. Live ClamAV/rescan not available. |
| H-17 | Medium | Inline theme script conflicted with a strict CSP. | `FIXED AND VERIFIED` | Theme bootstrap moved to `frontend/public/theme-init.js`; Nginx CSP allows `script-src 'self'` and the container serves the script. |
| H-18 | Low | Deployment/operations knowledge was not in a runbook. | `FIXED AND VERIFIED` | `docs/DEPLOYMENT.md` covers service roots, variables, build args, volume, ClamAV, migrations, health checks, TLS/HSTS, backups/PITR, monitoring, rollback, and smoke tests. |
| H-19 | Medium | Upload quotas were only per-file, not per-ticket. | `FIXED AND VERIFIED` | Per-ticket count/byte quotas with row locking; attachment tests cover rejection. |
| H-20 | Low | CI frontend build lacked the now-required production env. | `FIXED AND VERIFIED` | Workflow provides explicit non-secret CI build values; local build with the same values passes. |

### 5.3 External and operational checks

| Item | Status | Why |
| --- | --- | --- |
| Railway services, variables, volume, private networking | `NOT VERIFIED` | No Railway account access; no service was created or deployed. |
| Custom domains, TLS certificates, DNS | `NOT VERIFIED` | Provider-side action; no domain was changed. |
| PostgreSQL backups, PITR, restore drill | `NOT VERIFIED` | Requires the managed database plan and a disposable restore target. |
| Live shared Redis deployment | `NOT VERIFIED` | Local disposable Redis passed; production Redis was not provisioned. |
| Live ClamAV daemon and legacy attachment rescan | `NOT VERIFIED` | No scanner service was available; fail-closed behavior was tested, not a clean live scan. |
| GitHub Actions execution | `NOT VERIFIED` | Workflow is actionlint-clean but not executed on GitHub in this session. |
| Production Clerk sign-in, allowed origins, redirects | `NOT VERIFIED` | No production Clerk instance/credentials were used. |
| Monitoring, alerting, log retention | `NOT VERIFIED` | Railway/provider configuration not observed. |
| Browser E2E, accessibility, load/soak testing | `NOT VERIFIED` | Out of local test scope. |
| HSTS on public domains | `NOT VERIFIED` | Intentionally disabled until TLS and smoke tests are verified. |
| Commit/push/PR/deployment | `OPEN` | Not authorized by the task. |
| Root `package-lock.json` decision | `OPEN` | Ownership decision; unused by the frontend. |
| Five moderate dev-only npm advisories | `ACCEPTED RISK` | In `vitest`/`@vitest/ui`/`vite-plus` dev tooling; not production dependencies; production audit is clean. |
| Frontend production bundle size warning | `ACCEPTED RISK` | ~1.23 MB JS / 342 KB gzip works; code-splitting is a future performance task. |
| Single backend replica with local upload volume | `ACCEPTED RISK` | Current design; horizontal scaling requires shared object storage. |

---

## 6. Detailed changes and verified behavior

### 6.1 Supply chain: `certifi`

The advisory was independently checked at
`https://github.com/advisories/GHSA-6q48-6c7w-9gw2` (also `PYSEC-2026-4320`):

- affected range: `>= 2019.03.09, < 2026.10.18`;
- patched version: `2026.10.18`; the advisory recommends `2026.10.19+` so the
  unaffected eM Sign roots are restored;
- resolved version in `backend/uv.lock`: `2026.10.23`.

Actions:

1. verified the advisory and the lockfile's previous `2026.7.22` version;
2. ran `uv lock --upgrade-package certifi`;
3. confirmed `uv lock --check` resolves the project;
4. exported production-only requirements and ran `pip-audit --no-deps
   --disable-pip` against them: **No known vulnerabilities found**;
5. rebuilt the backend container, which installs `certifi==2026.10.23`.

`backend/pyproject.toml` and `backend/uv.lock` retain the pre-existing user
dependency changes; no unrelated pin was reverted.

### 6.2 Production configuration and startup

`backend/app/core/config.py` now rejects, in `ENVIRONMENT=production`:

- missing/non-HTTPS/path-bearing `FRONTEND_URL`, localhost origins, and wildcard
  CORS;
- non-`sk_live_` or placeholder Clerk keys;
- non-PostgreSQL/localhost/placeholder `DATABASE_URL`;
- Redis URLs that are not `redis://`/`rediss://`, localhost, or paired with
  disabled rate limiting/empty trusted proxies;
- invalid limiter windows/counts/timeout;
- disabled malware scanning, localhost/missing ClamAV, invalid scanner port or
  timeout;
- relative/temp `UPLOAD_DIR`, `AUTO_CREATE_TABLES=true`, `DATABASE_ECHO=true`;
- negative/zero pool, connect, recycle, statement, body, attachment, HSTS, or
  logging values;
- invalid log levels.

The check runs after Pydantic parsing and raises a plain `RuntimeError` naming
the variables, not the supplied secret values. Startup therefore fails before
serving traffic.

### 6.3 Request hardening and browser/API headers

`backend/app/core/middleware.py`:

- rejects `Content-Length` larger than the JSON or multipart limit immediately
  with `413 {"detail": "Request body is too large"}`;
- for chunked/unknown-length bodies, stops reading once the cap is crossed and
  replays only the bounded request;
- caps JSON at `MAX_JSON_BODY_BYTES` (1 MB default) and multipart at
  `MAX_UPLOAD_BYTES + MAX_MULTIPART_OVERHEAD_BYTES` (6 MB default);
- adds request IDs and structured request logs;
- adds CSP, `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`,
  `Referrer-Policy: no-referrer`, `Permissions-Policy`, COOP, and optional HSTS;
- adds `Cache-Control: no-store` to every `/api/` response, including error
  responses.

Swagger/ReDoc use development-only CSP allowances; API responses use
`default-src 'none'`. Production disables all three documentation routes.

### 6.4 API correctness and data integrity

- **Explicit nulls:** `PATCH /api/v1/tickets/{id}` and profile updates reject
  nulls for non-nullable columns with `422`, instead of allowing a database
  integrity failure.
- **Whitespace-only input:** trim-before-validate validators make
  whitespace-only titles/comments/feedback/staff/account-request text fail
  `min_length`; length limits are applied to ticket, comment, feedback, user,
  staff-message, internal-message, and account-request fields.
- **Integrity mapping:** only the `users.username` unique violation maps to
  `409 "Username is already taken"`; other user integrity failures return a
  generic data-conflict `409`. Ticket updates map unexpected integrity failures
  to a generic `409`.
- **Concurrency:** ticket update and claim paths load the row with `FOR UPDATE`;
  a PostgreSQL test verifies two concurrent updates serialize and the second
  observes the first commit.
- **Status timestamps:** `RESOLVED → CLOSED` preserves `resolved_at`;
  reopening/leaving `RESOLVED` clears it; entering `RESOLVED` sets it.
- **Upload quotas:** per-file size, allowed content type/signature, per-ticket
  attachment count, and per-ticket byte quota are enforced while the ticket row
  is locked.
- **Failure modes:** oversized uploads/body → `413`; invalid/blank input and
  infected uploads → `422`; rate limit → `429` with `Retry-After`; scanner or
  Redis unavailable → `503`; unauthorized → `401`/`403`.

### 6.5 Attachments and malware scanning

Uploads are written to a quarantine path, scanned with the ClamAV INSTREAM
adapter, and only a `CLEAN` result is published. `INFECTED` removes the bytes;
scanner errors fail closed with `503`. Downloads re-check ticket visibility,
scan status, and path containment.

Legacy `PENDING` attachments are rescanned on demand before download and can be
processed in bulk with:

```bash
python -m app.commands.scan_attachments
```

Migration `0009_attachment_scan_status` intentionally leaves existing files
`PENDING`; the one-off command requires the same upload volume as the API. A
live clamd and the real backlog remain `NOT VERIFIED`.

### 6.6 Owner conversations

`backend/app/services/staff_messages.py` replaces per-conversation queries with
bulk aggregate/latest-message queries and adds `limit`/`offset` pagination.
The conversation list is bounded and the summary query count is constant for a
page. Tests cover pagination and summary contents.

### 6.7 Database and migrations

`backend/app/core/database.py` configures `pool_pre_ping`, pool size/overflow,
pool timeout/recycle, connect timeout, and a server-side
`statement_timeout` for PostgreSQL. A PostgreSQL test verifies the psycopg
`options` value is applied (`SHOW statement_timeout` returned `1234ms` for the
test connection).

Migration evidence on the disposable database:

```text
alembic current  -> 0009_attachment_scan_status (head)
alembic check    -> No new upgrade operations detected.
downgrade 0008   -> success
upgrade head     -> success
alembic current  -> 0009_attachment_scan_status (head)
alembic check    -> No new upgrade operations detected.
```

No migration was created or edited for the CI `FRONTEND_URL` issue; that fix is
already in `e705144`/`e85345b`. Migrations remain the only production schema
mechanism; `AUTO_CREATE_TABLES` is local-only.

### 6.8 Frontend build and Nginx container

`frontend/src/lib/apiBase.ts` and `frontend/vite.config.ts` enforce production
`VITE_API_URL`:

- required;
- absolute HTTPS URL;
- no localhost/loopback host;
- exact origin only (no path/query/fragment).

`VITE_CLERK_PUBLISHABLE_KEY` is also required for a production build. The Nginx
container:

- serves the SPA and falls back to `index.html` for client routes;
- returns `404` for missing `/assets/*`;
- serves fingerprinted assets with
  `Cache-Control: public, max-age=31536000, immutable`;
- serves the shell with `Cache-Control: no-cache`;
- provides the Clerk-compatible CSP, security headers, and optional HSTS;
- validates `API_ORIGIN` and `CLERK_FAPI_ORIGIN` at container start.

The theme bootstrap is an external `/theme-init.js` file, not inline script, so
the strict CSP is compatible.

### 6.9 CI and dependency audits

`.github/workflows/ci.yml` now includes:

- backend lint/format/tests with a disposable Redis service;
- frontend typecheck/lint/tests/build with CI-only build values;
- a production frontend `npm audit --omit=dev --audit-level=high` gate;
- a production-only Python environment and `pip-audit`;
- disposable PostgreSQL migration/upgrade/downgrade checks;
- PostgreSQL integration tests.

The workflow is `actionlint` clean. Hosted execution is `NOT VERIFIED`.

### 6.10 Deployment assets and runbook

Added:

- `backend/Dockerfile` (Python 3.13, uv, non-root `app` uid 10001, `/data`
  volume prep, Uvicorn `${PORT}`);
- `backend/docker-entrypoint.sh` (root prepares uploads then `gosu app`);
- `frontend/Dockerfile` (Node build with `VITE_*` args; Nginx 1.29 runtime);
- `frontend/nginx.conf.template`, `frontend/docker-entrypoint.sh`;
- `backend/.dockerignore`, `frontend/.dockerignore`, `frontend/.env.example`,
  `frontend/.nvmrc`;
- `docs/DEPLOYMENT.md`, including Railway service roots, variables, build args,
  `/data` volume, ClamAV, pre-deploy `alembic upgrade head`, health checks,
  TLS/HSTS, backups/PITR, monitoring, rollback, and smoke commands.

Railway config-as-code is not added because it is deprecated; dashboard
configuration is documented instead.

---

## 7. Verification results

### 7.1 Backend

| Check | Result |
| --- | --- |
| `ruff format` / `ruff check` | **91 files unchanged; all checks passed** |
| Full pytest with disposable PostgreSQL and Redis | **413 passed, 20 skipped in 27.19 s** |
| `tests/test_production_hardening.py` | **55 passed** |
| `tests/test_postgres_integration.py` | **10 passed** |
| `tests/test_rate_limit.py` with Redis | **14 passed** |
| `tests/test_staff_messages.py` + hardening | **73 passed** |
| `uv lock --check` | **resolved 84 packages; pass** |
| `pip-audit` on exported production requirements | **No known vulnerabilities found** |

The 20 skipped cases are the opt-in demo-seed PostgreSQL suite guarded by
`HD_DEMO_SEED_POSTGRES_URL`; that separate suite is not re-run in this final
count. No persistent database was touched.

### 7.2 Frontend

| Check | Result |
| --- | --- |
| `npm run typecheck` | pass |
| `npm run lint` | pass |
| `npm test` | **5 files / 39 tests passed** |
| `npm run build` | pass; `index-*.js` 1,227.61 kB / 341.62 kB gzip, CSS 7.53 kB / 2.19 kB gzip |
| `npm audit --omit=dev --audit-level=high` | **found 0 vulnerabilities** |
| Full `npm audit` | 5 moderate dev-toolchain advisories; no high/critical and no production dependency is affected |
| Build with empty `VITE_API_URL` | fails with `VITE_API_URL is required for a production build` |

The chunk-size warning is a performance note, not a build failure.

### 7.3 Migrations and PostgreSQL

| Check | Result |
| --- | --- |
| Fresh/disposable PostgreSQL schema | pass |
| `alembic current` | `0009_attachment_scan_status (head)` |
| `0009` downgrade → `0008` | pass |
| `0008` upgrade → head | pass |
| `alembic check` before and after | `No new upgrade operations detected.` |
| PostgreSQL row-lock concurrency | pass |
| PostgreSQL statement timeout option | pass (`SHOW statement_timeout` → `1234ms` in the test connection) |

### 7.4 Docker and deployment smoke tests

**Backend image** (`helpdesk-backend:final`):

- built successfully with `uv sync --frozen --no-dev --no-install-project`;
- production container process ran as uid/gid `10001`;
- `/health/live` → `200`;
- `/health/ready` → `503` with
  `{"database":"ok","redis":"ok","clamav":"error"}` when ClamAV was intentionally
  unreachable;
- `/docs` and `/openapi.json` → `404`;
- unauthenticated `/api/v1/users/me` → `401` with `Cache-Control: no-store`;
- CSP, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`,
  `Permissions-Policy`, request ID, and optional HSTS headers observed;
- structured JSON request logs observed;
- a mounted upload directory was prepared and the app user was dropped to.

**Frontend image** (`helpdesk-frontend:final`):

- built with required build args;
- `/` → `200`; `/dashboard` and `/tickets/123` → `200` SPA shell;
- `/assets/<fingerprinted>.js` → `200` with immutable caching;
- `/assets/nope.js` → `404`;
- `/healthz` → `200`;
- CSP, COOP/CORP, Referrer-Policy, Permissions-Policy, `nosniff`, and optional
  HSTS observed;
- missing `API_ORIGIN`, HTTP `API_ORIGIN`, or a path/query origin causes startup
  failure with a clear error.

### 7.5 Security checks

- Production startup rejects invalid placeholders/localhost values and disabled
  controls (55 hardening tests).
- Body limits are enforced before parsing for declared-length and chunked
  multipart requests.
- API error and authenticated responses use `no-store`.
- Docs/OpenAPI are absent in production.
- Log redaction test covers bearer tokens, `sk_live_...`, PostgreSQL/Redis
  credential URLs, and password fields.
- `git diff --check` is clean.
- `actionlint` on the workflow reports no findings.

---

## 8. Residual risks and accepted trade-offs

1. **Railway is unprovisioned.** The runbook is complete, but no service,
   variable, volume, domain, certificate, backup, or monitor was created.
2. **ClamAV is unproven in production.** Fail-closed behavior is tested; a real
   scan of a benign upload and the legacy backlog is still required.
3. **Redis is locally verified only.** The Lua store and 503 fail-closed path
   pass against disposable Redis; production capacity/failover is unverified.
4. **Local volume is single-replica.** Uploads on `/data` require one backend
   replica; horizontal scaling needs an object store/shared filesystem.
5. **No E2E/a11y/load test.** Browser sign-in, Clerk redirects, and abuse/load
   behavior still need a disposable QA environment.
6. **Five moderate dev-only npm advisories** remain in the test toolchain.
   Production dependencies audit clean; forcing the suggested downgrade/version
   jump would be a larger toolchain change and is not justified without review.
7. **Frontend bundle size** is 1.23 MB JS / 342 KB gzip. Works, but code-splitting
   is a future optimization.
8. **Dirty tree.** Nothing is committed or pushed; the pre-existing
   `backend/pyproject.toml` / `backend/uv.lock` work was preserved.
9. **Root `package-lock.json`** remains a 7-line unused file; removing it is a
   repository-ownership decision.
10. **Backup/PITR is not proven.** A backup that has never been restored is not
    a verified recovery plan.

---

## 9. Remaining dashboard and external tasks

Complete these in order, with evidence:

1. **Authorize and create a commit/PR.** Review the 31 modified + 17 untracked
   files; do not include real `.env` files or secrets. Run CI on the PR.
2. **Railway services.** Create backend (`backend/`), frontend (`frontend/`),
   PostgreSQL, Redis, and a private ClamAV/clamd service.
3. **Backend variables.** Set `ENVIRONMENT=production`, production Clerk
   `sk_live_` secret, exact HTTPS `FRONTEND_URL`, PostgreSQL URL, Redis URL,
   `RATE_LIMIT_ENABLED=true`, non-empty trusted proxies, `MALWARE_SCAN_ENABLED=true`,
   `CLAMAV_HOST`/port, `UPLOAD_DIR=/data/uploads`, and
   `AUTO_CREATE_TABLES=false`.
4. **Backend volume.** Mount a Railway volume at `/data`; keep one backend
   replica for the current local-volume design.
5. **Frontend build/runtime variables.** Set build-time `VITE_API_URL` and
   `VITE_CLERK_PUBLISHABLE_KEY`; set runtime `API_ORIGIN` to the same API origin;
   rebuild after changing `VITE_*`.
6. **Migrations.** Take a PostgreSQL backup, run pre-deploy
   `alembic upgrade head`, check `alembic current` and `alembic check`, and keep
   `AUTO_CREATE_TABLES=false`.
7. **ClamAV and legacy files.** Wait for clamd signatures/health, run
   `python -m app.commands.scan_attachments` with the `/data` volume mounted,
   and verify a clean benign upload and an EICAR test only in disposable QA.
8. **Clerk.** Configure production allowed origins/redirect URLs for the final
   frontend and API domains; verify sign-in, token refresh, and sign-out.
9. **Domains/TLS.** Add custom domains, wait for verified certificates, then
   update `FRONTEND_URL`/`CORS_ORIGINS`/`VITE_API_URL`/`API_ORIGIN`.
10. **HSTS.** Only after TLS and smoke tests pass, set `HSTS_ENABLED=true` on
    both services. Keep `/docs`, `/redoc`, and `/openapi.json` disabled.
11. **Backups/PITR.** Enable the required retention, take a manual backup, and
    restore it into a disposable database.
12. **Monitoring.** Configure `/health/ready`, `/healthz`, 5xx/readiness/Redis/
    ClamAV/database alerts, log retention, and a spend limit.
13. **Smoke tests.** Run the commands in `docs/DEPLOYMENT.md` §8 against the
    real hostnames, including security headers, no-store, 404 docs, SPA fallback,
    asset caching, auth, upload, scan, and download.
14. **Decide** the root lockfile and record the authorized commit/deploy
    evidence. Until then, F-05/F-06 remain open.

---

## 10. Final verdict

**CONDITIONAL GO.**

The reviewed code, tests, migrations, container builds, and local production-mode
smoke checks pass. No unresolved code-level blocker was found in the tested
scope, and the critical `certifi` advisory is removed.

This is **not** a GO for public production traffic yet: Railway provisioning,
custom-domain TLS, hosted CI, a live ClamAV service and legacy rescan, a shared
Redis deployment, PostgreSQL restore/PITR, monitoring, and production Clerk
sign-in remain externally unverified. Complete §9, produce evidence, and then
run the final smoke suite. If the release cannot wait for those items, the
correct verdict is **NO-GO** for public production.

No production data was modified, no secret was exposed, and no commit, push,
merge, or deployment was performed.

---

## 11. Addendum: PR branch audit (`audit/production-readiness-pr`)

**Date:** 2026-10-29. This pass supersedes F-05 (dirty tree) and the
commit/PR row in §5.3: the remediation above is committed on a fresh branch
created from `origin/main` (`e85345b`) and proposed through a pull request.

### 11.1 History recovery

- `git-filter-repo` (run to redact Stripe-key-shaped fixtures) rewrote the
  shared history, so `oddit`'s base `e3f5663` and `origin/main` `e85345b`
  became different commits with an **identical tree**. Merging `origin/main`
  into `oddit` therefore produced add/add conflicts in every file the
  remediation touched, although there were no competing edits.
- The PR branch does not reuse `oddit`'s rewritten commits. The exact content
  delta `e85345b..oddit` (49 files) was re-applied as a new commit on
  `origin/main`, then reviewed and extended below.
- The originally flagged commit is not reachable from any ref in the working
  repository; it exists only in the offline backup bundle, which is not pushed.
  Clerk key fixtures in `backend/tests/test_production_hardening.py` are built
  at runtime from a prefix plus filler.

### 11.2 Additional findings

| ID | Severity | Finding | Status | Evidence / residual note |
| --- | --- | --- | --- | --- |
| H-21 | Low | Attachment download took a `FOR UPDATE` row lock before checking ticket visibility, and on every download, so any authenticated caller could hold locks on attachment rows and clean downloads were serialised. | `FIXED AND VERIFIED` | The row is read without a lock, visibility is checked, and only a `PENDING` rescan re-reads the row `FOR UPDATE`. Regression tests assert the call order; they fail on the previous code. |
| H-22 | Low | `SecurityHeadersMiddleware` rebuilt response headers as a dict, silently dropping repeated headers such as `Set-Cookie` and `Vary`. | `FIXED AND VERIFIED` | Headers are kept as a list and defaults are only appended when absent. Regression test fails on the previous code. |
| H-23 | Low | `docs/DEPLOYMENT.md` called `RATE_LIMIT_TRUSTED_PROXIES=0.0.0.0/0,::/0` acceptable, but with every hop trusted the limiter falls back to the edge peer, so all anonymous callers share one bucket. | `FIXED AND VERIFIED` (docs) | Runbook corrected; a test pins the fail-safe behaviour (no client-supplied hop is honoured). Choosing the real Railway edge ranges remains an operational task. |
| H-24 | Low | `test_production_hardening.py` was not `ruff format` clean after the history redaction, which would fail CI. | `FIXED AND VERIFIED` | `ruff format --check` is clean. |

External items in §5.3 and §9 (Railway, TLS, ClamAV, shared Redis, Clerk
production, backups, monitoring, hosted CI) remain `NOT VERIFIED`; this pass
did not change them.
