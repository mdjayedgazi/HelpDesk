# HelpDesk — Final production readiness report

**Report date:** 2026-11-21
**Repository:** https://github.com/mdjayedgazi/HelpDesk
**Base branch:** `main` @ `4c1bd00`
**Remediation branch:** `fix/production-readiness`
**Pull request:** [#19](https://github.com/mdjayedgazi/HelpDesk/pull/19) — open at the time of writing
**Final branch commit:** `cf19630` (before the merge, if one occurs)
**Environment reviewed:** Railway project `helpdesk-college-demo`, environment
`production`, services `helpdesk-api` and `helpdesk-web`.
**Deployment profile:** `college-demo` (explicit public-demo profile).

All results below were produced in this session. No historical result is
reported as current.

---

## A. Executive status

**CONDITIONALLY READY — for the college-demo deployment only.**

The repository code and the CI/CD pipeline are now correct and fully green:
every test suite, both Docker builds, the Helm chart, the disposable
PostgreSQL migration and integration suites, the secret scan, CodeQL, Trivy
image scans, and both SARIF uploads pass. The defect that broke CI before
(`Trivy` never ran because the pinned binary version had no release assets) is
fixed and proved.

It is **not** production-ready for real customers, and the report does not
claim otherwise. Four external prerequisites are unresolved and require account
access that this session does not have:

1. **Neon point-in-time recovery / backup retention** has not been verified, and
   no isolated restore drill has been performed.
2. **Clerk is still a development instance** (`sk_test_`/`pk_test_`). The
   `college-demo` profile tolerates this by design; a customer-facing production
   instance would not.
3. **Upstash Redis durability and ownership** could be partially observed
   (TLS works, PING succeeds) but the plan/durability/claim status cannot be
   verified without the Upstash dashboard.
4. **File storage is local-disk only**, which pins the backend to one replica.
   No object storage is configured. Attachments are currently **disabled**
   (`ATTACHMENTS_ENABLED=false`), so this is not an active risk in the current
   deployment.

The release pipeline, the migration gate, and the runtime configuration are
ready. What remains is account-level verification and configuration, not code.

---

## B. Git and backup

| Item | Value |
| --- | --- |
| Original branch | `fix/production-readiness` |
| Final branch | `fix/production-readiness` (reused; no new branch created) |
| Base commit | `4c1bd00` (`origin/main` at start and at finish) |
| Final commit | `cf19630` |
| Branch behind `main` | none — `git log HEAD..origin/main` is empty |
| Merge base | `4c1bd00` |
| Prior backup branch (preserved) | `wip/production-readiness-backup-20261121` @ `cf3f268` |
| New safety snapshot | `backup/production-readiness-pre-finalization-20261121` @ `e910fd4` |
| Backups pushed | no |

### Handling of pre-existing uncommitted work

On inspection the working tree had one modification: `data.md` had been
emptied (657 deletions, 0 bytes). Nothing was discarded:

- The diff was preserved outside the repository at
  `/tmp/opencode/helpdesk-safety/uncommitted-data-md-20261121.patch`.
- The committed version was also copied to
  `/tmp/opencode/helpdesk-safety/data.md.head-e910fd4`.
- The safety snapshot branch captured the branch HEAD (`e910fd4`).
- `data.md` was subsequently rewritten with the final review (this file's
  companion); the deleted content is recoverable from the patch and from
  `e910fd4`.

No `reset --hard`, `clean -fd`, `checkout -- .`, force-push, rebase, or branch
switch was used. The working tree was clean before any commit.

### Commits added in this session (on top of the previous remediation)

| Commit | Subject |
| --- | --- |
| `2cd55fa` | fix(ci): install a real Trivy release and make scans independent |
| `01a583f` | fix(api,db): allow Idempotency-Key preflight, keep timeouts zeroed |
| `2c9f7af` | fix(frontend): keep request timeout active while reading the body |
| `71cefc2` | test: guard disposable suites by database name, not URL substring |
| `af6b71b` | docs,ci: stop path-wide secret allowlists and fix backup commands |
| `cf19630` | fix(migrations): keep 0011 SQL generation working offline |

Total commits ahead of `main`: 15 (9 from the previous remediation + 6 here).

---

## C. Original remediation audit

Each item was re-checked against the real code before being trusted.

| # | Finding | Severity | Source | Status | Verification |
| --- | --- | --- | --- | --- | --- |
| 1 | Browser origins not normalized (trailing slash / default port breaks CORS and Clerk `azp`) | HIGH | `backend/app/core/config.py` | Fixed (prior) | `tests/test_origin_normalization.py` |
| 2 | No statement/lock timeout — a stuck query pins a pooled connection | MEDIUM | `backend/app/core/database.py` | Fixed here (see C1) | `tests/test_db_timeouts.py` |
| 3 | Readiness proved only connectivity, not schema | HIGH | `backend/app/core/health.py` | Fixed (prior) | `tests/test_readiness_schema.py`, live 503 test |
| 4 | Ticket creation not idempotent | MEDIUM | `backend/app/api/routers/tickets.py`, migration `0010` | Fixed (prior) | `tests/test_ticket_idempotency.py` |
| 5 | Missing list-ordering indexes | LOW/MEDIUM | migration `0011` | Fixed here (see C2) | `tests/test_query_indexes.py`, disposable PG |
| 6 | Frontend request could hang forever; no error boundary; one large bundle | MEDIUM | `frontend/src/lib/api.ts` | Fixed here (see C3) | `frontend/src/lib/api.test.ts` (52 tests) |
| 7 | Helm declared non-root nginx but image started as root | HIGH | `frontend/Dockerfile`, `helm/` | Fixed (prior) | Container run as uid 101, `helm lint`/`template` |
| 8 | CI unpinned actions, no type check, no Docker/security jobs | MEDIUM | `.github/workflows/ci.yml` | Fixed here (see D) | CI run `44901100310` all green |

### C1. New defect found in the remediation: zero timeouts were ignored

`_postgres_connect_args` omitted the libpq `options` when both timeout settings
were `0`. In PostgreSQL, omitting the option means "inherit the role default",
which is the opposite of "disable the limit". Fixed to always send an explicit
value. `tests/test_db_timeouts.py` now asserts the explicit zero.

### C2. New defect found in the remediation: migration 0011 was not upgrade-safe

`0011` created its indexes unconditionally while its own docstring documented
creating them `CONCURRENTLY` first for large tables. If an operator followed
that advice the migration would fail on the existing index name. `upgrade()` now
inspects the catalog and skips an already-indexed column set.

Verified on disposable PostgreSQL twice: same-named concurrent index
(`ix_tickets_created_at`) and a differently-named equivalent
(`some_operator_name`). Both converge to head with exactly one index per column
set. Offline SQL rendering also verified (see `cf19630`).

### C3. New defect found in the remediation: timeout cleared before the body was read

`fetch()` resolves when headers arrive; the cleanup ran in a `finally` attached
to that await, so the timeout and the caller's `AbortSignal` were removed before
`response.json()` completed. A stalled body could hang the UI forever. The new
test fails against the previous code (it hangs past the timeout) and passes now.

### C4. New defect found in the remediation: CORS rejected `Idempotency-Key`

The frontend sends `Idempotency-Key` on ticket creation, but `allow_headers` did
not list it. Starlette answers such a preflight with **400**. Confirmed against
the live API before the code fix:

```
OPTIONS /api/v1/tickets  (authorization,content-type)              -> 200
OPTIONS /api/v1/tickets  (authorization,content-type,idempotency-key) -> 400
```

That is a real, user-facing break in the current production topology (different
web and API origins). Fixed in `backend/app/main.py`; a regression test asserts
both the middleware list and an actual preflight response.

### C5. New defect found in the remediation: secret scan had path-wide allowlists

`.gitleaks.toml` excluded `backend/tests/**` and `backend/migrations/**` by path,
so a real credential committed there would never be reported. Replaced with
exact placeholder-value patterns. Proved with gitleaks 8.28.0:

- A fake `sk_live_` key under `backend/tests/` → **old config: no leaks found
  (missed)**; **new config: 1 leak, exit 1**.
- The repository itself still scans clean under the new config.

### C6. New defect found in the remediation: disposable-DB guard matched the whole URL

The PostgreSQL test suites searched the entire URL for `test`/`verify`/`ci`, so
`postgresql+psycopg://ci_runner:pw@db.example.com/helpdesk` passed. The suites
create tables and rows. The guard now parses the URL and checks only the
database name (including `?dbname=`), with its own tests.

### C7. Documentation defects fixed

`docs/DATABASE_BACKUP_RESTORE.md`:

- `pg_dump`/`pg_restore` were given `postgresql+psycopg://`, which libpq rejects.
  Scheme conversion added.
- The restore guard was a URL substring test (a `test`-containing password would
  pass; a valid Neon branch without a marker would fail). Replaced with a
  host/port/database identity comparison against `PRODUCTION_DATABASE_URL`.
- Verification read `RESTORE_DATABASE_URL` while the restore step set a
  different variable. Now both use the verified `RESTORE_LIBPQ_URL`.
- The schema probe was missing the required `FRONTEND_URL`. Added.
- No note that Alembic prefers `MIGRATION_DATABASE_URL`. Added.

`README.md`: the PostgreSQL container was started without waiting for readiness;
now a bounded `pg_isready` wait. The disposable-guard description matches the new
database-name check.

---

## D. Trivy and GitHub Actions

### D1. Root cause (from the actual job log, run `44895877917`, job `136821294963`)

The failure was **not** a vulnerability finding. `trivy-action@v0.33.1` defaults
its `version` input to **`v0.65.0`**. `setup-trivy` ran the official installer:

```
aquasecurity/trivy info checking GitHub for tag 'v0.65.0'
aquasecurity/trivy info found version: 0.65.0 for v0.65.0/Linux/64bit
##[error]Process completed with exit code 1.
```

The installer resolved the tag, then failed to download it. Verified directly:
the release assets for `v0.65.0` return **HTTP 404** (no published binary), while
`v0.70.0` returns **HTTP 302**. The tag exists on an empty release; the binary
does not. So the scanner binary was never installed, the scan never ran, and
`trivy-*.sarif` was never created.

The two `Path does not exist` errors and the skipped frontend scan are
downstream consequences: the failed backend step aborted the job before the
frontend scan ran, then `if: always()` uploads failed on the missing files.

### D2. Fix

| Item | Value |
| --- | --- |
| Trivy action | `aquasecurity/trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25` (v0.36.0) |
| Trivy binary | `v0.70.0`, passed explicitly as `version` |
| Checksum | `trivy_0.70.0_Linux-64bit.tar.gz` sha256 verified against the published `trivy_0.70.0_checksums.txt`: `8b4376d5d6befe5c24d503f10ff136d9e0c49f9127a4279fd110b727929a5aa9` |
| SARIF upload action | `github/codeql-action/upload-sarif@1bd86f2fdb4b86187fa4059f16f31a3202acc9ea` (v4.39.4, `node24`) |
| CodeQL init/autobuild/analyze | same v4.39.4 SHA |

The action SHA, the tag it belongs to, and the binary checksum were all verified
against the official repositories during this session.

### D3. Scanner independence and report validation

- Every build/scan/validate/upload step has its own `id`.
- A scan runs only when its own image built:
  `if: ${{ !cancelled() && steps.backend_build.outcome == 'success' }}`.
- A new validation step fails loudly if a successful scan produced no usable
  report (`test -s` + `jq` on `version == "2.1.0"` and a non-empty `runs`).
- Uploads run only after that validation succeeds and the file exists
  (`hashFiles(...) != ''`), each with a distinct `category`
  (`trivy-backend`, `trivy-frontend`) so two Trivy reports cannot collide.
- The report-only policy is unchanged: `severity: CRITICAL,HIGH`,
  `ignore-unfixed: true`, `exit-code: "0"`. Findings are reported; execution
  failures still fail the job.

### D4. Actual result (run `44901100310`, commit `cf19630`)

```
Build backend image                       success
Build frontend image                      success
Frontend image serves health / non-root    success
Trivy image scan (backend)                success  (installed v0.70.0)
Validate backend SARIF report             success
Upload backend scan                       success  ("Successfully uploaded results")
Trivy image scan (frontend)               success  (ran, not skipped)
Validate frontend SARIF report            success
Upload frontend scan                      success
```

Locally the same binary produced valid SARIF for both images (backend 44
results, frontend 58 results) with exit code 0.

---

## E. Test results (this session)

### Backend

| Check | Command | Result |
| --- | --- | --- |
| pytest (SQLite) | `uv run pytest -q` | **456 passed, 47 skipped** |
| pytest (+ disposable PostgreSQL) | same, with `HD_TEST_POSTGRES_URL` / `HD_DEMO_SEED_POSTGRES_URL` | **502 passed, 1 skipped** |
| Ruff lint | `uv run ruff check .` | passed |
| Ruff format | `uv run ruff format --check .` | 113 files already formatted |
| Pyrefly | `uv run pyrefly check` | 0 errors |
| Alembic upgrade | `alembic upgrade head` on disposable PG | OK, head `0011_query_indexes` |
| Alembic drift | `alembic check` | "No new upgrade operations detected" |
| Alembic offline SQL | `alembic upgrade 0009:head --sql` | renders all statements |
| `0009 → 0011` with data | rows inserted at `0009`, then upgraded | 1 user / 1 ticket / 1 notification preserved |
| Retry safety | `alembic upgrade head` twice | second run is a no-op |
| Downgrade/re-upgrade | `0011 → 0010 → head` | counts preserved |
| Failure propagation | unreachable DB | `alembic` exits 1 |

### Frontend

| Check | Command | Result |
| --- | --- | --- |
| Typecheck | `npm run typecheck` | passed |
| Lint | `npm run lint` | passed |
| Unit tests | `npm test` | **52 passed** (8 files) |
| Production build | `npm run build` (CI env) | passed; entry 453.62 kB (122.12 kB gzip) |
| Production audit | `npm audit --omit=dev --audit-level=high` | **0 vulnerabilities** |

The 47 backend skips are the opt-in PostgreSQL suites when no disposable URL is
set. The 1 remaining skip with PostgreSQL enabled is an intentional Redis-only
opt-in that had no disposable Redis in this local run; CI runs it against its
own `redis:7-alpine` service.

### Infrastructure

| Check | Result |
| --- | --- |
| Backend Docker build | passed |
| Frontend Docker build | passed |
| Frontend runs as uid | `101` (asserted) |
| `/healthz` | `ok` |
| Unknown asset | `404` |
| Security headers | `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, full CSP present |
| Backend image user | `10001` (`app`) |
| Backend container as non-root | starts, serves `/health/live` |
| Backend readiness (migrated DB) | `{"status":"ready","checks":{"database":"ok","schema":"ok",...}}` |
| Helm lint | 1 chart linted, 0 failed |
| Helm template (default + ingress) | both render |
| Trivy backend SARIF | valid, 44 results, exit 0 |
| Trivy frontend SARIF | valid, 58 results, exit 0 |
| Gitleaks (repo history, 62 commits) | no leaks |
| Gitleaks (injected real key) | detected, exit 1 |
| `actionlint` | clean |
| `git diff --check` | clean |

### GitHub Actions (run `44901100310`, head `cf19630`)

All eight jobs `success`: Backend lint and SQLite tests, Frontend typecheck/lint/
tests/build, Production dependency audit, PostgreSQL integration tests,
Alembic migrations (disposable PostgreSQL), Docker image builds, Helm chart
validation, Static security analysis and secret scan. CodeQL and both SARIF
uploads succeeded.

---

## F. Neon database and recovery

All production database access was **read-only** (`read_only=True`,
`transaction_read_only=on`). No write, DDL, reset, or restore was performed.

| Item | Observed |
| --- | --- |
| Host type | Neon, **pooled** (`-pooler`) endpoint |
| PostgreSQL version | 18.7 |
| Region/plan metadata | not available without the Neon console |
| Current revision | **`0009_attachment_scan_status`** |
| Tables | all expected application tables present |
| `users` | 1 (role `CUSTOMER`, active, linked to Clerk, created 2026-11-19) |
| `tickets` / `comments` / `attachments` / `notifications` | 0 / 0 / 0 / 0 |
| `tickets.client_request_id` | **absent** (expected at `0009`) |
| Indexes | only pre-`0011` indexes present |
| Database size | 8744 kB |
| Runtime role | `neondb_owner` (not superuser) |

### Historical user-count discrepancy

The prior audit recorded one user, then zero, with no cause determined. The
current database has **one** CUSTOMER created on 2026-11-19. No audit trail,
backup metadata, or recovery point is reachable without the Neon console, so
**the cause of the earlier zero remains undetermined**. No restoration was
attempted or is recommended: there is no evidence of current data loss.

### Backup / PITR

**Not verified.** Neon PITR availability, retention, and restore-point
inventory require the Neon console (or `neonctl`, which is not installed and has
no stored credential). No isolated restore branch was created and **no restore
was performed**; this report does not claim one succeeded. See section L.

### Release-critical interaction

Production is at `0009`, while the merging image ships `0011` and its readiness
probe is **production-fatal when the revision differs**. Without a migration
gate the new image would fail `/health/ready` and never receive traffic. This
made the migration gate in section J a release blocker, not an enhancement.

Verified for release:

- The production URL is reachable by Alembic and reports `0009` (a live
  `alembic current` through Railway's variables, read-only).
- `0009 → 0011` preserves existing rows on disposable PostgreSQL.
- The migrations are additive (one nullable column + partial unique index, two
  non-unique indexes); the previous `0009` application remains compatible with
  the expanded schema, so an application rollback does not require a downgrade.
- A failed migration exits non-zero, which fails the Railway pre-deploy.

---

## G. Clerk and ownership

| Item | Observed |
| --- | --- |
| Backend secret key | **`sk_test_*`** (Clerk development instance) |
| Frontend publishable key | **`pk_test_*`** |
| Clerk FAPI origin | `https://social-ferret-6540.clerk.accounts.dev` |
| `DEPLOYMENT_PROFILE` | `college-demo` (permits `sk_test_` by design) |
| Session verification | enforced server-side; `authorized_parties` = configured origins |
| `azp` validation | enabled via the same origin allowlist |
| User sync | server derives identity from Clerk; never trusts client roles |
| Protected endpoints | `/api/v1/users/me` returns **401** unauthenticated (verified live) |
| Interactive sign-in | **UNVERIFIED** — no authorized test Clerk account was provided |

The `college-demo` profile is the only configuration that accepts a Clerk
development secret, and it does so explicitly. A customer-facing deployment
must use a production Clerk instance (`sk_live_`/`pk_live_`); the `standard`
profile already refuses `sk_test_`.

### Owner

Not verifiable from outside: whether an OWNER row exists depends on whether the
one-time bootstrap command was run. The database currently holds **no OWNER**
(the single user is a CUSTOMER). `INITIAL_ADMIN_EMAIL` is not among the API
service's variable names, so bootstrap is not configured in this environment.

- `bootstrap_owner` is idempotent and promotes only an already-linked account
  whose **verified** Clerk primary email matches `INITIAL_ADMIN_EMAIL`.
- A CUSTOMER cannot become OWNER by any request path; there is no runtime
  elevation.
- **No promotion was performed.** The exact procedure (owner action) is in
  section L.

---

## H. Upstash Redis

All Redis operations were read-only (`PING`, `INFO`, `DBSIZE`, `ACL WHOAMI`).
No `FLUSHALL`/`FLUSHDB`, no writes, no delete.

| Item | Observed |
| --- | --- |
| URL scheme | `rediss://` (TLS) |
| `PING` | `PONG` |
| Server version | 8.4.0 |
| Auth identity | `default` |
| Current keys | 0 (`db0` empty) |
| Max memory | 64 MB, policy `optimistic-volatile` |
| Durability (`appendonly`, RDB) | not reported by `INFO` — **unverified** |
| Ownership / claim / expiry | **unverified** (requires Upstash console) |
| Railway linkage | present as `RATE_LIMIT_REDIS_URL` on `helpdesk-api` |

The application fails closed if Redis is unreachable at startup, and
`/health/ready` reports `redis: ok` in the live deployment. Whether the database
is temporary/unclaimed, and its durability settings, cannot be confirmed from
the connection alone; see section L. No replacement was made.

---

## I. File storage

| Item | Status |
| --- | --- |
| Current architecture | Local filesystem under `UPLOAD_DIR` (`/data/uploads`) |
| Attachments in this deployment | **disabled** (`ATTACHMENTS_ENABLED=false`) |
| Upload authorization | requires an authenticated user with ticket visibility |
| Size limits | 5 MiB/file, 20 files/ticket, 50 MiB/ticket, body middleware pre-check |
| MIME + magic bytes | allowlist plus signature check (PNG/JPEG/GIF/PDF/ZIP/Office) |
| Malware scanning | synchronous ClamAV INSTREAM, **fail-closed**; no "disabled = clean" path |
| Quarantine | written to `.quarantine`, moved only after `CLEAN` |
| Path containment | resolved inside the storage root; download authorized before use |
| Durability | local volume only — **single replica required** |
| Replicas | `numReplicas: 1` (confirmed on both services) |

Because there is no shared storage, horizontal scaling must stay at one replica.
That is the current setting and was not changed.

### R2 vs S3

For this application, **Cloudflare R2** is the better first target:

- S3-compatible API, so the storage layer can be implemented once.
- No egress charge, which fits a support desk that serves attachment downloads.
- Private buckets with presigned URLs map directly onto the existing
  authorize-then-download flow.
- Lifecycle rules cover quarantine cleanup.

Amazon S3 remains the better choice if the deployment later needs AWS IAM
integration, cross-region replication, or existing AWS billing. No object
storage was implemented: that requires a provider decision and credentials.

---

## J. Railway deployment

The project, environment and services were verified before any change.

| Item | Value |
| --- | --- |
| Project | `helpdesk-college-demo` (`d59fbf51-…`) |
| Environment | `production` (`126b1644-…`) |
| API service | `helpdesk-api` (`3ffa5eab-…`), root `/backend` |
| Web service | `helpdesk-web` (`a1f2359d-…`), root `/frontend` |
| Repository | `mdjayedgazi/HelpDesk` on both |
| Trigger branch | `main` on both |
| Wait for CI (`checkSuites`) | **true** on both |
| API healthcheck | changed `/health/live` → **`/health/ready`** |
| Web healthcheck | `/healthz` |
| Healthcheck timeout | 300 s |
| Replicas | 1 each |
| API pre-deploy command | **added: `alembic upgrade head`** |
| API domain target port | `8080` (matches injected `PORT`) |
| Web domain target port | `8080` |
| Current deployed commit | `169f76e` (both services) |
| `.env`/secrets printed | never |

### Changes applied (only the two settings required for a safe release)

Applied to `helpdesk-api` via the Railway GraphQL API, after confirming IDs and
that the running image already exposes `/health/ready` (200 on `main`):

1. `preDeployCommand: ["alembic upgrade head"]`
2. `healthcheckPath: "/health/ready"`

`sleepApplication: true` was required by the Free plan on this mutation and was
already set, so it was preserved. No other setting, variable, volume, domain,
port, or service was modified; no service was created or recreated.

### Why this is correct

- The pre-deploy runs in the **backend image's** working directory `/app`, where
  `alembic` is on `PATH` (`/app/.venv/bin/alembic`). Verified inside the built
  image, as both `root` and the runtime `10001:10001` user.
- Railway aborts the release when the pre-deploy exits non-zero. A failed
  migration exits 1 (verified against an unreachable database).
- Only after the migration does the new container start, and then only
  `/health/ready` (which checks schema equality) clears it for traffic.
- The migrations are additive, so the previous `0009` application stays
  compatible during the rollout and for an application rollback.

### Healthcheck and port

The API listens on `$PORT` (`CMD` uses `${PORT:-8000}`), Railway injects `8080`,
and the public domain targets `8080`. Confirmed consistent. `/health/live`
remains the liveness probe.

### Automatic deployment

Both services already deploy from `main` with Wait-for-CI enabled, so a merged
commit that passes CI is the deployment trigger. No `railway up` deployment was
created.

---

## K. Pull request and merge

| Item | Value |
| --- | --- |
| PR | [#19](https://github.com/mdjayedgazi/HelpDesk/pull/19) |
| Title | "Fix/production readiness" |
| Source → target | `fix/production-readiness` → `main` |
| Commits | 15 |
| Conflict status | `mergeable: MERGEABLE`, `mergeStateStatus: CLEAN`, 0 behind `main` |
| Required checks | all 8 CI jobs + CodeQL + Trivy + CodeRabbit: success |
| Branch protection | **none configured** on `main` |
| Review decision | none required/enforced |

All earlier CodeRabbit findings that were real defects were fixed and are
covered in section C. The CodeRabbit "pin CodeQL to a real commit" and "distinct
SARIF category" findings are addressed by the new pins and categories.

**Merge status: not merged in this session.** Section M explains the gate that
was intentionally left to the owner.

---

## L. Outstanding blockers and manual steps

Each item lists why it matters, whether code changes are needed, and whether it
blocks a college-demo versus customer-facing release.

### L1. Neon PITR and restore drill — account access required

- **Unresolved:** PITR window, retention, restore-point inventory, and whether a
  restore works have not been observed.
- **Why it matters:** the runbook requires a *tested* restore. An untested
  backup is not a backup.
- **Code changes:** none.
- **Blocks:** customer-facing production. Not the current college demo.
- **Steps:** in the Neon console, record the plan and PITR window; create a
  branch from a recent point in time; run the section 4 verification in
  `docs/DATABASE_BACKUP_RESTORE.md` against that branch; record host/port/db,
  counts, and `alembic_version`. Never restore over production.

### L2. Clerk production instance — account access required

- **Unresolved:** the deployment uses a Clerk development instance.
- **Why it matters:** development keys are not appropriate for real customers.
- **Code changes:** none; `standard` already refuses `sk_test_`.
- **Blocks:** customer-facing production only.
- **Steps:** create a Clerk production instance, add the production domains,
  put `sk_live_…` on `helpdesk-api` and `pk_live_…` on `helpdesk-web` (rebuild
  the frontend, since `VITE_` values are compile-time), set `FRONTEND_URL` to
  the production origin, and remove `DEPLOYMENT_PROFILE=college-demo`. Rotate
  keys — do not paste them into chat.

### L3. OWNER bootstrap — authorization required

- **Unresolved:** no OWNER exists; `INITIAL_ADMIN_EMAIL` is not configured.
- **Why it matters:** owner-only administration (user management, internal
  messages) is unavailable.
- **Code changes:** none.
- **Blocks:** administrative use of the deployment.
- **Steps:** sign in once with the intended admin account (creates a linked
  CUSTOMER), set `INITIAL_ADMIN_EMAIL` to that verified Clerk primary email,
  run `python -m app.commands.bootstrap_owner` once in the API environment, then
  remove the variable. It is idempotent and promotes only a verified, linked
  match. **Do not run it without authorization.**

### L4. Upstash durability/ownership — account access required

- **Unresolved:** claim status, expiry, plan, and persistence settings.
- **Why it matters:** rate limiting fails closed, so an evicted or expired
  database returns 503 for protected routes.
- **Code changes:** none.
- **Blocks:** customer-facing production certainty; the demo is functioning.
- **Steps:** in the Upstash console, confirm the database is claimed, has no
  expiry, and has a persistence/eviction policy appropriate for rate-limit
  keys. Record the plan and the TLS endpoint's ownership.

### L5. Durable object storage — decision + credentials required

- **Unresolved:** attachments are on local disk and disabled.
- **Why it matters:** horizontal scaling and durable uploads need shared
  storage.
- **Code changes:** yes, when implemented (storage adapter + signed URLs).
- **Blocks:** enabling attachments at more than one replica.
- **Steps:** choose R2 (recommended) or S3, provision a private bucket, add the
  credentials as service variables, and implement the adapter. Keep one replica
  until then.

### L6. Interactive authenticated verification — credentials required

**UNVERIFIED.** No authorized Clerk test account was available, so sign-in,
`/users/me`, ticket creation, assignment, comments, notifications, claim, and
sign-out were **not** exercised through a real session. Unauthenticated access
control *was* verified (401 on `/api/v1/users/me`). Do not treat the
authenticated flow as tested.

### L7. Minor, non-blocking

- Remaining `Node.js 20 deprecated` annotations come from third-party actions
  (`setup-uv`, `gitleaks-action`, `setup-helm`, `checkout`) that still declare a
  Node 20 runtime and are being force-run on Node 24. CI is green; this is a
  warning, not a failure. Upgrade those pins when the vendors release Node 24
  metadata.
- The Trivy SARIF includes all severities by design (`limit-severities-for-sarif`
  unset). Findings are report-only, as intended.

---

## M. Final recommendation

**CONDITIONALLY READY.** The merged code and pipeline are correct, the
migration gate is in place and proven safe, and all automated gates pass.

This is a college-demo environment. A merge into `main` now would (a) run
`alembic upgrade head` against Neon as a pre-deploy, (b) refuse the release if
that fails, and (c) only route traffic once `/health/ready` reports a matching
schema — which is exactly the safe sequence this repository needed. The schema
change is additive, so rollback does not require a downgrade.

The merge was **not** performed in this session because it is the one action
that mutates production data (via the pre-deploy migration) and the request
explicitly requires stopping before production-data operations it cannot
supervise. Every prerequisite the owner can check without side effects has been
checked; the remaining steps (L1–L5) are account-level configuration. Once the
owner confirms those (or explicitly accepts the college-demo limitations) and
merges PR #19, Railway will deploy `main` automatically under the verified
gates. Then verify with:

```bash
API=https://helpdesk-api-production-1dc9dd39.up.railway.app
WEB=https://helpdesk-web-production-d96f8e2b.up.railway.app
curl -fsS "$API/health/live"
curl -fsS "$API/health/ready"      # must show schema: ok at 0011 after deploy
curl -fsS "$WEB/healthz"
curl -s -o /dev/null -w '%{http_code}\n' "$API/api/v1/users/me"   # expect 401
```

Do not describe this deployment as production-ready for real customers until
L1 (tested recovery), L2 (production Clerk), and L4 (durable Redis) are closed,
and attachments (L5) are on shared storage before any scale-out.
