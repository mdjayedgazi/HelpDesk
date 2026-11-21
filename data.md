# HelpDesk — production readiness remediation review

**Review date:** 2026-11-21
**Repository:** `mdjayedgazi/HelpDesk`
**Base branch:** `main` @ `4c1bd00`
**Remediation branch:** `fix/production-readiness`
**Branch URL:** https://github.com/mdjayedgazi/HelpDesk/tree/fix/production-readiness
**Pull request (not opened automatically):** https://github.com/mdjayedgazi/HelpDesk/pull/new/fix/production-readiness
**Status:** **PARTIALLY READY — EXTERNAL CONFIGURATION REQUIRED.**

The repository-side fixes for every confirmed HIGH and MEDIUM issue are
implemented, tested, and pushed as a reviewable branch. Several items remain
that require Neon, Clerk, Upstash, Railway, or object-storage account access;
those are documented, not claimed as done.

> The prior audit from 2026-11-19 is preserved verbatim at the end of this file
> under **Appendix A — Previous audit (2026-11-19)**.

---

## 0. How this work was performed (safety first)

The working tree was reviewed **before any edit**. It was found on a local
branch `fix/production-readiness` that had no commits of its own, with
uncommitted changes and untracked files that already matched this remediation
scope (idempotency, indexes, readiness, CORS normalization, health).

Per the task's safety rules, that pre-existing work was **not** discarded,
stashed, overwritten, or committed blindly:

- It was committed as-is to a local-only backup branch
  `wip/production-readiness-backup-20261121` (`cf3f268`). This branch was **not
  pushed**.
- The remediation was then rebuilt from a clean `origin/main` baseline,
  re-verifying each finding against the current code rather than trusting the
  prior work.
- Two defects in the prior work were found and corrected:
  1. Its `_postgres_connect_args` helper was written but **never wired into the
     engine**, so statement timeouts would not have applied.
  2. Its index migration added partly redundant indexes that duplicated
     existing single-column indexes.
- No `git reset --hard`, `git clean -fd`, force push, database reset, migration
  deletion, `.env` overwrite, volume removal, or destructive production
  operation was performed.

`origin` was verified as `https://github.com/mdjayedgazi/HelpDesk.git`, and the
remote default branch is `main` (not `master`). The new branch was created from
the latest `origin/main` and pushed only as a branch; `main` was never modified.

---

## 1. Baseline (historical results reproduced first)

Before editing, the audit's historical baseline was reproduced locally so any
later regression could be attributed correctly:

| Check | Baseline result |
| --- | --- |
| Backend `pytest` (SQLite, Clerk stubbed) | 404 passed, 45 skipped |
| Frontend `npm test` | 42 passed |
| Backend Ruff lint + format | pass |
| Backend type check (pyrefly) | 0 errors |
| Frontend typecheck + lint | pass |
| `npm audit --omit=dev --audit-level=high` | 0 vulnerabilities |
| Frontend production build | 1 JS chunk, 1,227.97 kB (341.78 kB gzip) |

These matched the historical audit, so the baseline was intact.

---

## 2. Confirmed issues and fixes

Each item below was verified against the current code before changing it. The
fix is minimal and targeted; working features and API contracts were preserved.

### 2.1 HIGH — `/health/ready` checked only `SELECT 1`

- **Files:** `backend/app/core/health.py`, `backend/alembic.ini`,
  `backend/tests/test_readiness_schema.py`
- **Why it was a problem:** `SELECT 1` proves connectivity but says nothing
  about whether the expected schema exists or whether migrations have been
  applied. A half-migrated or empty database would report "ready".
- **Fix:** added a read-only `schema` check that (a) reads the single Alembic
  head shipped in the image, (b) verifies the required core tables exist, and
  (c) compares them with the live `alembic_version`. Non-`ok` is fatal (`503`)
  only when `ENVIRONMENT=production`; in development/test (where tables may come
  from `AUTO_CREATE_TABLES`) it is reported but not fatal. Output stays coarse
  (`ok` / `outdated` / `incomplete` / `unknown`) — no connection string, host,
  or exception text is exposed. The head is read once and cached.
- **Also:** set `alembic.ini` `path_separator = os` to silence the deprecation
  warning the probe would otherwise emit.
- **Preserved:** `/health/live` behavior is unchanged (pure liveness).

### 2.2 HIGH — `FRONTEND_URL` / CORS trailing-slash origin mismatch

- **Files:** `backend/app/core/config.py`,
  `backend/tests/test_origin_normalization.py`
- **Why it was a problem:** browsers send `Origin` and Clerk sends `azp`
  **without** a trailing slash or a redundant default port. An operator-pasted
  value like `https://app.example.com/` passed startup validation but never
  matched, silently breaking CORS preflight and Clerk verification.
- **Fix:** `allowed_origins` now normalizes each origin to
  `scheme://host[:port]` (strip trailing slash; drop `:443`/`:80`). It is used
  for both CORS and the `azp` check, so one allowlist governs both. A value that
  carries a path/query/fragment is **not** normalized — the production validator
  still rejects it, so an unintended URL is never silently accepted. Exact
  origin semantics for CORS are preserved.
- **Tests:** trailing slash/es/whitespace, default-port equivalence,
  path/wildcard left untouched, de-duplication, and production acceptance of a
  trailing slash plus rejection of a path-bearing origin.

### 2.3 HIGH — ticket creation could duplicate on retry

- **Files:** `backend/app/api/routers/tickets.py`,
  `backend/app/models/ticket.py`,
  `backend/migrations/versions/0010_ticket_idempotency.py`,
  `backend/tests/test_ticket_idempotency.py`
- **Why it was a problem:** a retried `POST /api/v1/tickets` (lost response,
  double click, network retry) created a second ticket; only the ticket
  *number* was protected against collision.
- **Fix:** an optional `Idempotency-Key` header. A nullable
  `tickets.client_request_id` column plus a **partial unique index**
  `(created_by_user_id, client_request_id) WHERE client_request_id IS NOT NULL`
  guarantees one ticket per creator/key. A repeated request returns the original
  ticket. A concurrent duplicate that wins the insert is resolved by re-reading
  the winning row; the conflict test mirrors the existing ticket-number
  handling (SQLSTATE + constraint name, with a SQLite message fallback).
- **Backward compatible:** no header ⇒ behavior is exactly as before; existing
  rows keep `NULL` and are excluded from the partial index; the column is never
  exposed in `TicketRead`.
- **Tests:** repeat, distinct, absent, blank, invalid, cross-creator, simulated
  lost-race, DB uniqueness, and many-`NULL` rows.

### 2.4 MEDIUM — no PostgreSQL statement/lock timeout

- **Files:** `backend/app/core/database.py`, `backend/app/core/config.py`,
  `backend/.env.example`, `backend/tests/test_db_timeouts.py`
- **Why it was a problem:** one pathological query or lock wait could pin a
  pooled connection until the client disconnected; with a small pool that stalls
  unrelated requests.
- **Fix:** `DB_STATEMENT_TIMEOUT_MS` (default 15000) and `DB_LOCK_TIMEOUT_MS`
  (default 5000), applied as libpq `options` on **direct** PostgreSQL endpoints.
  PgBouncer-style pooled endpoints (Neon `-pooler`) keep only the
  prepared-statement fix, because they do not reliably honour per-connection
  startup options; the docs say to set the same limits on the database role
  there. `0` disables a limit.
- **Verified live** against disposable PostgreSQL: `SHOW statement_timeout`
  returned `250ms` and a `pg_sleep(1)` was interrupted (`OperationalError`)
  when configured to 250ms.

### 2.5 MEDIUM — missing, justified query indexes

- **Files:** `backend/app/models/notification.py`,
  `backend/app/models/ticket.py`,
  `backend/migrations/versions/0011_query_indexes.py`,
  `backend/tests/test_query_indexes.py`
- **Why it was a problem:** every ticket list orders by `created_at DESC` with
  `LIMIT/OFFSET`, and the notification panel lists one recipient newest-first;
  neither ordering was indexed.
- **Justification:** the indexes were chosen from the actual queries, not
  speculatively. Added `tickets.created_at` and
  `notifications(recipient_user_id, created_at)`. The notification index's
  leading column still serves plain recipient lookups, so no duplicate index was
  added. The prior WIP's broader set was deliberately **not** copied because
  parts duplicated existing single-column indexes.
- **Tests:** declared metadata, column order, and a duplicate-multi-column guard.

### 2.6 MEDIUM — missing frontend request timeout

- **Files:** `frontend/src/lib/api.ts`, `frontend/src/lib/api.test.ts`
- **Why it was a problem:** a hung connection left a mutation pending forever
  and the UI stuck on a spinner.
- **Fix:** an internal `AbortController` with a default 20 s request timeout and
  a 120 s upload timeout, combined with the caller's `AbortSignal` (e.g. React
  Query cancellation). A timeout surfaces a clear message; a genuine
  cancellation still rejects with `AbortError`. Timers are always cleared.

### 2.7 MEDIUM — missing React ErrorBoundary

- **Files:** `frontend/src/components/ErrorBoundary.tsx` (+ test),
  `frontend/src/main.tsx`
- **Fix:** an application-level error boundary around `<App/>` with a
  recoverable fallback (Try again / Reload). It logs the error to the console
  only; no user data is shown.

### 2.8 MEDIUM — large single JS bundle (~1.23 MB)

- **Files:** `frontend/src/App.tsx`
- **Fix:** route-level `React.lazy` + `Suspense`. Routing, guards, and API
  contracts are unchanged; only load timing differs. The single chunk became a
  **453.54 kB (122.08 kB gzip)** entry plus per-route chunks, all under the
  500 kB warning threshold.

### 2.9 MEDIUM — Helm nginx user/`runAsNonRoot` mismatch; API not routable

- **Files:** `frontend/Dockerfile`,
  `helm/helpdesk/{values.yaml,templates/frontend-deployment.yaml,templates/ingress.yaml}`
- **Why it was a problem:** the chart declared `runAsNonRoot: true` and
  `readOnlyRootFilesystem: true` for the frontend, but the official
  `nginx:1.29-alpine` image started as **root** (verified) — so the pod would
  fail to start under those constraints. Separately, the Ingress exposed only
  the web service, while the SPA calls the API on an absolute origin.
- **Fix:** the image now chowns the writable config/cache/log paths and the pid
  file to the `nginx` user and switches to `USER 101:101`. The chart pins the
  matching numeric ids and adds pod-level `fsGroup: 101` so the emptyDir mounts
  are writable on a read-only root. Added an **opt-in** `ingress.apiHosts` block
  (default empty ⇒ rendered output unchanged) that routes a separate API host to
  the backend service.
- **Verified:** built the image, ran it as uid 101, confirmed `/healthz` `200`,
  SPA fallback `200`, missing asset `404`, and full security headers. `helm
  lint` and `helm template` (default and ingress variants) pass.

### 2.10 MEDIUM — CI/CD hardening

- **Files:** `.github/workflows/ci.yml`, `.gitleaks.toml`,
  `backend/tests/test_e2e_support_flow_postgres.py`
- **Fixes:**
  - Every action pinned to a **verified full commit SHA**: checkout `v4.2.2`,
    setup-node `v4.4.0`, setup-uv `v6.6.1`, codeql-action `v3.30.0`,
    trivy-action `v0.33.1`, gitleaks-action `v2.3.9`, setup-helm `v4.3.1`,
    upload-sarif `v3.30.0`. Each SHA was resolved from the real tag via
    `git ls-remote`; none were invented.
  - Backend job now also runs `pyrefly check`; the migrations job runs
    `alembic check`.
  - New `docker-build` job builds both images, asserts the frontend image runs
    as uid `101` and serves `/healthz`, and uploads Trivy **SARIF** to the
    Security tab. Gating is intentionally left non-blocking (`exit-code: "0"`)
    because unfixed base-image CVEs must not red every PR; the doc explains how
    to turn it on after reviewing the baseline.
  - New `helm` job lints and renders the chart.
  - New `security` job runs a gitleaks secret scan and CodeQL (free for this
    public repository).
  - **E2E:** a new isolated PostgreSQL test covers authentication → ticket
    creation → automatic assignment, plus the agent claim flow. It runs only
    against a disposable database (guarded by the existing
    `test|verify|ci` name check) and adds no deploy/production steps.
- **Preserved:** the existing Railway deployment behavior is untouched; no
  workflow step modifies production infrastructure on a pull request.

### 2.11 Documentation

- **Files:** `docs/DATABASE_BACKUP_RESTORE.md` (new),
  `docs/PRODUCTION_READINESS.md` (new), `docs/DEPLOYMENT.md`,
  `docs/RAILWAY_COLLEGE_DEMO.md`, `backend/migrations/README.md`, `README.md`
- Added a backup/restore runbook with a **disposable-only restore guard** and
  restore verification; an external-configuration guide covering Clerk
  production, Upstash ownership/durability, and the object-storage decision; the
  new DB timeout settings; and corrections to stale notes (single-chunk bundle,
  trailing-slash behavior). The migrations README documents `0010`/`0011`.

---

## 3. Deliberately NOT changed

- **Authentication / authorization architecture** — Clerk verification, role
  authority, customer-only provisioning, and all permissions preserved.
- **Upload security** — magic-byte validation, ClamAV fail-closed scanning,
  quarantine → publish, path containment, and authorization preserved. No
  asynchronous/queue upload pipeline was introduced (no proven need, and it
  would be a larger correctness risk).
- **Synchronous ClamAV scanning** — reviewed; the architecture has no worker,
  and fail-closed synchronous scanning is correct as-is. Left unchanged.
- **Object storage (S3/R2)** — not implemented. No provider access, and a
  half-built backend would be riskier than the current single-replica volume.
  Multi-replica deployment remains explicitly forbidden until a migration is
  verified; `replicaCount` stays `1`.
- **Redis eviction/persistence** — not changed; requires verifying the actual
  Upstash account. No `FLUSHALL`/`FLUSHDB` was run and `REDIS_URL` was never
  printed.
- **Foreign-key deletion behavior / cascades** — not added.
- **HSTS** — remains opt-in and unchanged (documented decision).
- **Docker base-image digest pinning** — reviewed; left on tags as before (out
  of scope, and not a confirmed defect).
- **Existing tests** — none removed or weakened.

---

## 4. Validation (final, on the committed tree)

| Check | Result |
| --- | --- |
| Backend `pytest` (SQLite) | **448 passed, 47 skipped** |
| Backend Ruff lint | pass |
| Backend Ruff format | 111 files formatted |
| Backend type check (pyrefly) | **0 errors** |
| Frontend typecheck | pass |
| Frontend lint | pass (0 warnings) |
| Frontend tests | **50 passed** |
| `npm audit --omit=dev --audit-level=high` | **0 vulnerabilities** |
| Frontend production build | entry **453.54 kB / 122.08 kB gzip**, route chunks |
| Docker backend build | ok; container starts, `/health/live` `200` |
| Docker frontend build | ok; runs as uid `101`, `/healthz` `200`, SPA `200`, missing asset `404` |
| Helm lint / template (default + ingress) | pass |
| Alembic on disposable PostgreSQL | `upgrade head` ok, `alembic check` **“No new upgrade operations detected.”**, `0011→0010→0009 → head` re-upgrade ok |
| PostgreSQL integration + E2E | **26 passed** (incl. auth→create→assignment and claim) |
| `git diff --check` | clean |
| Secret scan of committed diff | no real secrets (only `.env.example` placeholders) |

**Disposable-PostgreSQL-only.** Every database check ran against throwaway
Docker containers (`POSTGRES_DB` names containing `verify`/`hdverify`), never a
real database. The E2E and integration modules refuse any URL that does not look
disposable.

**Regression accounting:** the 44 new backend tests and 8 new frontend tests are
additive; no baseline test was modified to pass. No pre-existing failure was
hidden.

**CI execution status:** the workflow triggers on `pull_request` and pushes to
`main`, so it has **not run yet** — no PR was opened (per instructions, the
branch is published for review, not merged). All workflow commands were
exercised locally first.

---

## 5. Remaining external / manual items (not completed here)

These require account access this environment does not have. Each is documented
in `docs/PRODUCTION_READINESS.md` or `docs/DATABASE_BACKUP_RESTORE.md` with the
exact dashboard location, the environment variable **names** (never values), and
how to verify success.

1. **Neon backups / PITR / restore drill** — confirm plan, PITR window,
   retention, and perform a restore **into an isolated branch**. No backup or
   restore is claimed to have succeeded.
2. **Clerk production instance** — create/own it, configure allowed origins,
   set `sk_live_`/`pk_live_` and `CLERK_FAPI_ORIGIN`, then rotate live Railway
   credentials with owner authorization. Code already fails closed on a
   non-`sk_live_` key outside the explicit college-demo profile.
3. **Upstash ownership/durability** — claim the database before it expires and
   confirm plan/eviction/persistence in the console. No settings were changed.
4. **Object storage (S3/R2)** — decide and provision; keep one replica until the
   migration is verified.
5. **Railway dashboard** — no production variables/ports/volumes/deploys were
   changed. Confirm the web service still passes its healthcheck now that the
   image runs as uid 101.
6. **Monitoring/alerting** — wire `/health/ready`, DB connection saturation, and
   backup-status alerts in Neon/Railway or your monitoring provider.

---

## 6. Git

| Item | Value |
| --- | --- |
| Repository | `https://github.com/mdjayedgazi/HelpDesk` |
| Default branch | `main` (untouched at `4c1bd00`, verified via `ls-remote`) |
| New branch | `fix/production-readiness` (local-only backup of prior WIP: `wip/production-readiness-backup-20261121`, not pushed) |
| Push result | new branch pushed; `origin/main` unchanged |
| Branch URL | https://github.com/mdjayedgazi/HelpDesk/tree/fix/production-readiness |

Commits (oldest → newest):

```
1ee60b3 fix(config): normalize browser origins and add DB query timeouts
fa9be12 feat(health): check schema/migration state in readiness
e517783 feat(tickets): make ticket creation idempotent
322ae3c perf(db): add indexes for ticket and notification list ordering
08c94a8 feat(frontend): add request timeouts, ErrorBoundary, and code splitting
f1e71b9 fix(helm): run nginx unprivileged and route the API ingress
10566fb ci: pin actions, add type check, docker/E2E/security jobs
23dadd9 docs: add backup/restore and production-readiness runbooks
```

---

## 7. Final assessment

**PARTIALLY READY — EXTERNAL CONFIGURATION REQUIRED.**

Automated tests pass and the repository-side remediation is complete and
reviewable, but production readiness is not declared from test results alone.
The remaining blockers are operational and external: verified Neon
backup/PITR + a real restore drill, a Clerk production instance with rotated
credentials, confirmed Upstash ownership/durability, and the object-storage
decision before any horizontal scaling.

---

# Appendix A — Previous audit (2026-11-19)

The following is the prior audit, preserved verbatim for history. Some statements
below were superseded by this remediation (for example the single-chunk bundle
size and the trailing-slash behavior), as detailed in sections 2.2 and 2.8 above.

## HelpDesk — production connectivity audit and Railway verification

**Review date:** 2026-11-19
**Repository:** `mdjayedgazi/HelpDesk`
**Branch:** `main`
**Commit under test:** `169f76e645550e97e2f616ac9677018dc174777f` (PR #18 merge)
**Railway project:** `helpdesk-college-demo`, environment `production`, region `ams`
**Services:** `helpdesk-api`, `helpdesk-web`
**Status:** **API and frontend are live and reachable. Redis and PostgreSQL are healthy. Interactive Clerk sign-in and the authenticated dashboard remain unverified because no test credentials exist.**

---

### A. Root causes

#### A1. Dashboard failure (fixed this pass) — Railway domain target port did not match the container port

The API deployment had already reached `SUCCESS` and Uvicorn was listening on
`http://0.0.0.0:8080`, but every request to the public API origin timed out with
no HTTP response, or returned `502` at the Railway edge.

| Evidence | Value |
| --- | --- |
| Service domain | `helpdesk-api-production-1dc9dd39.up.railway.app` |
| Domain target port before the fix | **`8000`** |
| Container port from startup log | **`8080`** (`Uvicorn running on http://0.0.0.0:8080`) |
| Source of `8080` | Railway injects `PORT=8080` at runtime; the image default is `PORT=8000` |
| Public `GET /health/live` before the fix | `000` (connection opened, no bytes) / intermittent `502` |
| Deployment status at the same time | `SUCCESS`, container healthy |
| Container-side healthcheck | Passed (Railway's own probe reached the container) |

The API image sets `PORT=8000`, but Railway's runtime `PORT` overrides it to
`8080`. The public domain still targeted `8000`, so the edge had no listener to
route to. The container was healthy, which is why the deployment gate passed and
why this looked like a frontend or database problem rather than routing.

That failure surfaces in the browser exactly as reported: `fetch` rejects
(`ApiError(0)`), and the UI shows **"Could not reach the HelpDesk server. Check
your connection."** The profile request never reaches FastAPI, so
`/api/v1/users/me` never appears in the API logs.

**Fix:** set the API service domain target port to `8080`, matching the running
container. No application code change was required.

#### A2. Earlier startup failure (fixed previously) — missing `RATE_LIMIT_REDIS_URL`

The first API deployment (`0964f512-468b-4edd-a5e2-d32be2ad04c2`) crashed during
`Settings._validate_production_configuration()`:

```text
RuntimeError: Invalid production configuration:
RATE_LIMIT_REDIS_URL must be a redis:// or rediss:// URL
```

`ENVIRONMENT=production` + `RATE_LIMIT_ENABLED=true` require a TLS Redis URL.
The variable was absent. A real Upstash `rediss://` database was provisioned,
verified over TLS (`PING`, `SET`, `GET`, `DEL`), and configured through secure
stdin. The API then started and passed `/health/live`.

#### A3. Operational risk — the first Redis database was temporary

The first database came from Upstash's no-signup agent endpoint. Those databases
live for three days unless claimed, and the claim/console link was not retained
by the first provisioning script. A **fresh, retry-safe database** was created
with a saved claim link and Railway was switched to it (verified by host hash).
It still expires in three days unless claimed. See section E.

#### A4. Configuration observation — Clerk development instance

The frontend build uses `VITE_CLERK_PUBLISHABLE_KEY` starting with `pk_test_`,
i.e. a Clerk **development** instance (`social-ferret-6540.clerk.accounts.dev`).
Clerk works and the FAPI host matches the CSP exactly, but a development
instance is not appropriate for a long-lived production site. This is not the
cause of the dashboard failure.

---

### B. Component status

| Component | Status | Evidence |
| --- | --- | --- |
| Railway API | **PASS** | Deployment `75e9a9df-fe69-4c1e-ac46-4f6e421b3709`, `SUCCESS`, root `/backend`, `backend/Dockerfile`, branch `main`, commit `169f76e` |
| API liveness | **PASS** | `GET /health/live` → `200` `{"status":"ok"}` |
| API readiness | **PASS** | `GET /health/ready` → `200` `{"status":"ready","checks":{"database":"ok","redis":"ok","clamav":"disabled"}}` |
| Neon PostgreSQL | **PASS** | `SELECT 1` → `1`; PostgreSQL `18.7`; pooled host; `sslmode=require`; Alembic `0009_attachment_scan_status` (head) |
| Upstash Redis | **PASS (temporary)** | `rediss://` TLS; direct `PING`/`SET`/`GET`/`DEL` succeeded; readiness reports `redis: ok`; database expires in 3 days unless claimed |
| Clerk authentication | **PARTIAL** | Clerk JS loads, sign-in form renders, no console errors; no interactive sign-in performed (no test credentials) |
| Frontend API URL | **PASS** | `VITE_API_URL=https://helpdesk-api-production-1dc9dd39.up.railway.app`; correct origin, no path; present in the compiled bundle |
| CORS | **PASS** | Preflight `OPTIONS` → `200`, exact origin allowed, credentials on, `Authorization` allowed, rate-limit/request-id headers exposed |
| CSP | **PASS** | API + Clerk FAPI + telemetry + bot-protection origins present; no `unsafe-eval`; no Railway wildcard; no empty substitution |
| Dashboard profile endpoint | **PARTIAL** | `/api/v1/users/me` → `401` without a token (correct, CORS headers present); success path untested without a session |
| User synchronization | **CODE REVIEW OK / UNVERIFIED LIVE** | `get_current_user` links by verified Clerk email or provisions `CUSTOMER`; no live signed-in request available |
| Dashboard UI | **PARTIAL** | `/dashboard` loads `200`; unauthenticated visit redirects to `/sign-in`; signed-in rendering untested |

---

### C. Changes implemented

#### Railway configuration (no code change)

| Change | Value |
| --- | --- |
| `RATE_LIMIT_REDIS_URL` on `helpdesk-api` | Replaced with a fresh Upstash `rediss://` URL, set via `railway variable set --stdin` from a mode-`600` temporary file, which was deleted immediately |
| `helpdesk-api` public domain target port | `8000` → `8080` (matches the running container / injected `$PORT`) |
| API deployment | Redeployed from `main` `169f76e` after the changes |

#### Documentation

| File | Change |
| --- | --- |
| `data.md` | This review |
| `docs/RAILWAY_COLLEGE_DEMO.md` | Corrected the API port to `$PORT` (observed `8080`) and documented that the service domain target port must match the container port |

#### Not changed

- No application code, schema, migration, or test was modified.
- No Railway service, volume, or paid resource was added.
- No database write, migration, reset, or record create/delete was performed.
- Production security settings were preserved (section F).

---

### D. Deployment evidence

| Item | Value |
| --- | --- |
| Deployed commit | `169f76e645550e97e2f616ac9677018dc174777f` |
| API deployment ID | `75e9a9df-fe69-4c1e-ac46-4f6e421b3709` (`SUCCESS`) |
| API deployment root / Dockerfile | `/backend` / `Dockerfile` |
| API healthcheck path | `/health/live`, 300 s timeout |
| API healthcheck result | Passed; container stays running |
| API public origin | `https://helpdesk-api-production-1dc9dd39.up.railway.app` |
| Web deployment ID | `96ac72c1-e946-4f7c-b497-32244124a253` (`SUCCESS`, sleeps when idle) |
| Web deployment root | `/frontend`, commit `169f76e` |
| Web public origin | `https://helpdesk-web-production-d96f8e2b.up.railway.app` |
| CI on merge commit | `CI` run `44090500688` — success |

#### D1. Live HTTP results (after the fix)

| Request | Result |
| --- | --- |
| `GET /health/live` | `200` |
| `GET /health/ready` | `200` — database `ok`, redis `ok`, clamav `disabled` |
| `GET /docs` | `404` |
| `GET /redoc` | `404` |
| `GET /openapi.json` | `404` |
| `GET /api/v1/users/me` (no token) | `401` `{"detail":"Invalid or missing Clerk session"}`, `WWW-Authenticate: Bearer` |
| `GET /api/v1/tickets` (no token) | `401` |
| `POST /api/v1/tickets/<id>/attachments` (no token) | `503` (attachments disabled, rejected before auth/upload) |
| `OPTIONS /api/v1/users/me` (frontend origin) | `200`, exact-origin CORS |
| `GET /api/v1/does-not-exist` | `404` |
| Web `/` | `200` |
| Web `/dashboard` | `200` (SPA shell) |
| Web `/sign-in` | `200` |
| Web `/healthz` | `200` |
| Web asset `assets/index-BaVIDY5W.js` | `200` |

#### D2. Redis

| Check | Result |
| --- | --- |
| URL scheme | `rediss://` (TLS), host suffix `.upstash.io` |
| Direct connectivity | `PING` true; `SET`/`GET`/`DEL` round-trip true |
| Server | Redis `8.4.0` |
| Railway host match | Host hash `87fbf133d893` matches the newly provisioned database |
| App readiness | `redis: ok` on every `/health/ready` check |
| Secrets | URL never printed, never passed as an argument, never logged; temp file deleted; no `rediss://` string in runtime logs |

#### D3. Neon PostgreSQL

Same database as the previous review (local config host hash `e880522f1db4`
equals the Railway config host hash; database `neondb`, role `neon`, pooled
endpoint, `sslmode=require`).

| Check | Result |
| --- | --- |
| `SELECT 1` | `1` |
| Server version | PostgreSQL `18.7` |
| Alembic current | `0009_attachment_scan_status` (head) |
| `users` | **0** |
| `tickets` | `0` |
| `comments` | `0` |
| `attachments` | `0` |
| `users` columns | `id, clerk_id, full_name, username, email, password_hash, role, is_active, created_at, updated_at, image_url` |

The `users` count is `0` now; the 2026-11-17 review recorded `1`. This audit
issued only `SELECT`/`SHOW` statements against PostgreSQL (and one `SET`/`GET`/
`DEL` probe on Redis). The row was not removed by this review. See section E.

#### D4. Frontend bundle and CSP

| Check | Result |
| --- | --- |
| Deployed bundle | `assets/index-BaVIDY5W.js`, `1,228,227` bytes |
| API origin in bundle | Present (`2` occurrences) |
| `http://127.0.0.1:8000` | Only in the production-guard branch (`VITE_API_URL is required for a production build`); not reachable in this build and not allowed by CSP |
| `VITE_API_URL` shape | Exact HTTPS origin, no path/query; validated by `apiBase.ts` at build time |
| `VITE_ATTACHMENTS_ENABLED` | `false` |
| Clerk FAPI in CSP | `https://social-ferret-6540.clerk.accounts.dev` |
| Publishable key FAPI match | Yes (decoded key host equals the CSP FAPI host) |
| Clerk telemetry / bot-protection origins | Present |
| `unsafe-eval` | Absent |
| Railway API wildcard | Absent |
| Empty substitutions | None |

Headless Chromium on the live `/sign-in` page:

- `window.Clerk` defined and Clerk script loaded.
- Sign-in form rendered; title `HelpDesk · Support, without the chaos`.
- No console errors, no failed Clerk script loads (only aborted bot-protection
  probes, which are normal challenge traffic).
- One benign CSP violation: `script-src` blocks `Function("")` inside a
  feature-detection helper in the app bundle. The call is wrapped in
  `try/catch` and falls back to `jitless` mode, so it has no functional impact.
- `/dashboard` while signed out redirects to `/sign-in`; no API calls are made
  before authentication, so no spurious "connection" error appears.

---

### E. Remaining problems and required manual actions

| Item | Detail |
| --- | --- |
| **Claim the Upstash database** | The current Redis database is a temporary no-signup database. It expires **3 days after creation** unless claimed. The claim/console link is stored outside the repository at `~/.local/state/helpdesk/upstash-claim.url` (mode `600`, directory `700`). Open it, sign in to Upstash, and click **Claim**; otherwise the API will start failing within three days. |
| **No Owner account** | `users` is empty and `INITIAL_ADMIN_EMAIL` is not set, so no OWNER exists. The first Clerk sign-in provisions a `CUSTOMER` automatically. To get an OWNER, set `INITIAL_ADMIN_EMAIL` and run the one-time bootstrap: `uv run python -m app.commands.bootstrap_owner` from `backend/`. This is a deliberate manual step and was not performed. |
| **Interactive Clerk sign-in** | Not tested: no test credentials and no authorization to create production users. The sign-in page, Clerk script, FAPI origin, and CSP are verified. |
| **Authenticated dashboard** | Not tested for the same reason. The endpoint contract, 401 behavior, CORS, and the auto-provisioning code path were reviewed. |
| **Live rate-limit `429`** | Not triggered. The limiter protects authenticated write endpoints; without a session the request stops at `401`. Redis reachability and startup validation are verified through `/health/ready` and a direct TLS ping. |
| **Clerk instance is `pk_test_`** | Development instance. Functional for a college demo; switch to a production Clerk instance for a durable production deployment. |
| **Cold start** | The container was observed stopping and starting again and served `200` afterwards. A full scheduled sleep→wake cycle was not measured end to end. |
| **`users` table emptied** | Between 2026-11-17 and 2026-11-19 the single row disappeared. Cause not determined; this audit performed no writes. Existing ticket/comment/attachment data was already empty and remains empty. |

---

### F. Production configuration preserved

| Control | State |
| --- | --- |
| `ENVIRONMENT` | `production` |
| `DEPLOYMENT_PROFILE` | `college-demo` |
| `RATE_LIMIT_ENABLED` | `true` |
| `RATE_LIMIT_REDIS_URL` | `rediss://` (TLS) |
| `ATTACHMENTS_ENABLED` | `false` |
| `MALWARE_SCAN_ENABLED` | `false` |
| `AUTO_CREATE_TABLES` | `false` |
| `FRONTEND_URL` | exact Railway web origin |
| CORS | exact origin only; credentials on; no wildcard |
| CSP / security headers | intact on the live frontend |
| Neon PostgreSQL | unchanged, at Alembic head, no writes |
| Clerk auth / role authorization | unchanged; `401` enforced on protected routes |
| Attachments | still rejected (`503`) |
| Service topology | exactly two services; no volume, no paid resource |

No rate-limit bypass, auth bypass, unscanned upload path, development profile,
or wildcard CORS was introduced.

---

### G. Conclusion

The dashboard was not failing because of Neon. It was failing because the public
Railway domain for `helpdesk-api` targeted port `8000` while Railway ran the
container on `8080`. The deployment and container were healthy; only the edge
route was wrong. Aligning the domain target port to `8080` restored the API, and
`/health/ready` now confirms both PostgreSQL and Redis.

The API is live on commit `169f76e` (deployment
`75e9a9df-fe69-4c1e-ac46-4f6e421b3709`), the frontend is live on the same commit,
CORS and CSP are correct, unauthenticated access is rejected with `401`, and
attachments remain disabled. The only unverified link in the chain is a real
Clerk session, which requires credentials this environment does not have.

Two manual follow-ups remain: **claim the Upstash database before it expires**,
and **bootstrap an OWNER** if administrative access is needed.
