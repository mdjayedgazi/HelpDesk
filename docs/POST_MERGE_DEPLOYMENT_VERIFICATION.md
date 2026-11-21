# HelpDesk — Post-merge Railway deployment verification

**Report date:** 2026-11-21
**Repository:** https://github.com/mdjayedgazi/HelpDesk
**Merge PR:** [#19](https://github.com/mdjayedgazi/HelpDesk/pull/19) — **merged**
**Main commit verified:** `2ca6930f16ee0e502c4c6d97912fae0592efd2ef`
**Post-merge CI run:** [44902233062](https://github.com/mdjayedgazi/HelpDesk/actions/runs/44902233062)
**Railway project:** `helpdesk-college-demo` / environment `production`
**Final conclusion:** **DEPLOYMENT VERIFIED** (for the college-demo profile) —
see section 7 for the readiness classification.

Every statement below was produced from live inspection in this session: git
state, GitHub Actions, the Railway GraphQL API and logs, read-only database and
Redis queries, and public HTTP requests. GitHub CI results alone were never
treated as proof of deployment.

---

## 1. GitHub status

| Item | Verified value |
| --- | --- |
| PR #19 state | **MERGED** at `2026-11-21T12:06:07Z` |
| Merge commit | `2ca6930f16ee0e502c4c6d97912fae0592efd2ef` |
| `origin/main` | exactly `2ca6930` — **no newer commit exists** |
| PR #19 not reopened / not re-merged | confirmed |
| Backups preserved | `backup/production-readiness-pre-finalization-20261121` = `e910fd4`; `wip/production-readiness-backup-20261121` = `cf3f268` |
| Local working tree | `data.md` was emptied again before this session; preserved to `/tmp/opencode/helpdesk-postmerge/` and restored to HEAD (no loss) |

### Post-merge CI run `44902233062` (commit `2ca6930`)

All eight jobs succeeded:

```
Backend lint and SQLite tests                    success
Frontend typecheck, lint, tests, build           success
Production dependency audit                      success
Alembic migrations (disposable PostgreSQL)       success
PostgreSQL integration tests (disposable)        success
Docker image builds                              success
Helm chart validation                            success
Static security analysis and secret scan         success
```

Docker job steps, all `success`:

```
Build backend image / Build frontend image
Frontend image serves health and runs as non-root
Trivy image scan (backend)       -> Validate backend SARIF  -> Upload backend scan
Trivy image scan (frontend)      -> Validate frontend SARIF -> Upload frontend scan
```

The Trivy binary installed was `v0.70.0` (the previously broken default
`v0.65.0` is gone), so the earlier root-cause fix holds in production CI.

### Node.js 20 deprecation warnings

The post-merge run emitted **8** Node.js 20 warnings, from five actions:

```
actions/checkout, actions/setup-node, astral-sh/setup-uv,
azure/setup-helm, gitleaks/gitleaks-action
```

These are warnings only and did not fail any job. A separate maintenance PR
addresses them (section 6).

---

## 2. Railway status

Project, environment and service identities were confirmed before inspecting
anything: project `helpdesk-college-demo` (`d59fbf51-…`), environment
`production` (`126b1644-…`), repo `mdjayedgazi/HelpDesk` on both services.

### Backend — `helpdesk-api`

| Item | Value |
| --- | --- |
| Service ID | `3ffa5eab-83ee-49f6-bda5-b7fdfd08ac0d` |
| Latest deployment ID | `ae9667c2-be0d-4747-8f07-beac5f49c202` |
| Deployment status | **SUCCESS** |
| Deployed commit | **`2ca6930f…`** (the merge commit) |
| Source branch | `main` |
| Repository connection | `mdjayedgazi/HelpDesk`, root `/backend` |
| Build | Dockerfile build succeeded (image digest `sha256:51e1ed00…`) |
| Pre-deploy | `alembic upgrade head` — **ran, see section 3** |
| Healthcheck | `/health/ready`, 300 s, **"Healthcheck succeeded!"** in build log |
| Runtime | Uvicorn on `http://0.0.0.0:8080` (injected `PORT`) |
| Public domain | `https://helpdesk-api-production-1dc9dd39.up.railway.app`, target port **8080** |
| Replicas | 1 |
| Wait for CI | enabled |

### Frontend — `helpdesk-web`

| Item | Value |
| --- | --- |
| Service ID | `a1f2359d-2d9f-4293-bec7-6b20122fdfca` |
| Latest deployment ID | `2b89dac8-d3ab-4fc0-af19-4f356f56d7eb` |
| Deployment status | **SUCCESS** |
| Deployed commit | **`2ca6930f…`** |
| Source branch | `main` |
| Repository connection | `mdjayedgazi/HelpDesk`, root `/frontend` |
| Build | Dockerfile build succeeded |
| Pre-deploy | none (not needed; static assets) |
| Healthcheck | `/healthz`, 300 s — passed |
| Runtime | nginx unprivileged, port `8080` |
| Public domain | `https://helpdesk-web-production-d96f8e2b.up.railway.app`, target port **8080** |
| Replicas | 1 |
| Wait for CI | enabled |

### Both services run the same commit

Both deployments are `2ca6930f…`, the current `origin/main`. Neither is the old
`169f76e`, neither is partial, and neither is pending or failing. Because this
is a Free-plan project with `sleepApplication: true`, `helpdesk-web` shows
`SLEEPING` while idle; it woke and returned `200` on request (section 4).

`helpdesk-api` reports `running: 1, crashed: 0` and its latest deployment status
is `SUCCESS`.

### Deployment logs inspected

- API build: Dockerfile stages completed, image exported and pushed, then
  `Starting Healthcheck / Path: /health/ready / [1/1] Healthcheck succeeded!`.
- API runtime: `Starting Container` → startup → `Uvicorn running on
  http://0.0.0.0:8080`, with `GET /health/ready 200` entries and normal request
  logs.
- Web runtime: nginx started and served `/`, `/sign-in`, `/dashboard`,
  `/assets/...` with the expected status codes; `/assets/nope.js` → `404`.

No secret, connection string, or variable value was printed at any point.

---

## 3. Database status (Neon PostgreSQL)

All access was read-only (`transaction_read_only = on`).

**Pre-deploy execution evidence** — from the API deployment log:

```
Starting Container
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade 0009_attachment_scan_status -> 0010_ticket_idempotency
INFO  [alembic.runtime.migration] Running upgrade 0010_ticket_idempotency -> 0011_query_indexes
Starting Container
INFO:     Started server process [1]
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080
```

This is the Railway pre-deploy step. The application container started **after**
both migrations. No manual migration was run.

### Verified schema state

| Check | Result |
| --- | --- |
| Alembic revision | **`0011_query_indexes`** (was `0009` before the merge) |
| `tickets.client_request_id` | present, `character varying(100)`, nullable |
| `uq_tickets_creator_request_key` | present, unique, partial `WHERE client_request_id IS NOT NULL` |
| `ix_tickets_created_at` | present |
| `ix_notifications_recipient_created_at` | present |
| Core tables | all 14 application tables present |
| PostgreSQL version | 18.7 (Neon branch `br-damp-tooth-b5t0ckbx`) |
| Runtime DB role | `neondb_owner`, not superuser |
| Database size | 8712 kB (8744 kB at first inspection — normal churn) |

### Data preserved

Before the merge the database held 1 user (CUSTOMER, created 2026-11-19) and
0 tickets/comments/attachments/notifications. After the migration it holds
**the same 1 CUSTOMER**, with the same creation date, and the same zero counts
elsewhere. The migration was additive and preserved all existing rows.

`/health/ready` returns:

```json
{"status":"ready","checks":{"database":"ok","schema":"ok","redis":"ok","clamav":"disabled"}}
```

Three consecutive probes returned the same result, so schema readiness is stable.

No migration failure occurred, so no rollback or recovery was needed.

---

## 4. Live HTTP smoke tests

Domains used were confirmed from the Railway API before testing (section 2).

### Backend

| Request | Status | Notes |
| --- | --- | --- |
| `GET /health/live` | **200** | `{"status":"ok"}` |
| `GET /health/ready` | **200** | database/schema/redis `ok` |
| `GET /api/v1/users/me` (no auth) | **401** | correct — protected |
| `GET /api/v1/tickets` (no auth) | **401** | correct — protected |
| `GET /api/v1/does-not-exist` | **404** | correct |

The unauthenticated `401`s are the intended access-control behavior, not
failures.

### Frontend

| Request | Status | Notes |
| --- | --- | --- |
| `GET /` | **200** | SPA shell, title `HelpDesk · Support, without the chaos` |
| `GET /sign-in` | **200** | sign-in route renders SPA shell |
| `GET /dashboard` | **200** | SPA shell (client-side route; guard handles auth in-app) |
| `GET /healthz` | **200** | `ok` |
| `GET /assets/index-DjyIAN11.js` | **200** | 453,682 bytes |
| `GET /assets/nope.js` | **404** | missing asset handled |

Security headers present on `/`:

```
content-security-policy: default-src 'self'; ... connect-src 'self'
  https://helpdesk-api-production-1dc9dd39.up.railway.app
  https://social-ferret-6540.clerk.accounts.dev ...; frame-ancestors 'none'
x-content-type-options: nosniff
x-frame-options: DENY
referrer-policy: strict-origin-when-cross-origin
permissions-policy: camera=(), microphone=(), geolocation=(), payment=(), usb=()
cross-origin-opener-policy: same-origin-allow-popups
cross-origin-resource-policy: same-origin
```

The deployed JS bundle contains the correct API origin
`https://helpdesk-api-production-1dc9dd39.up.railway.app`, so the build-time
origin matches the running service.

### CORS verification (the previously broken path)

Preflight for ticket creation with `authorization,content-type,idempotency-key`:

```
OPTIONS /api/v1/tickets   Origin: <web origin>
  Access-Control-Request-Headers: authorization,content-type,idempotency-key
-> HTTP/2 200
   access-control-allow-origin: https://helpdesk-web-production-d96f8e2b.up.railway.app
   access-control-allow-headers: Accept, Accept-Language, Authorization,
     Content-Language, Content-Type, Idempotency-Key, X-Request-ID
   access-control-allow-methods: GET, POST, PATCH, PUT, DELETE, OPTIONS
   access-control-allow-credentials: true
```

A disallowed origin (`https://evil.example.com`) is still rejected with `400`,
so the allowlist was widened only by the one required header, not weakened.
No ticket was created.

---

## 5. Deployment safety

| Item | API | Web |
| --- | --- | --- |
| Runtime port | injects `PORT` (`8080`), Uvicorn binds `0.0.0.0:$PORT` | `8080` |
| Domain target port | `8080` | `8080` |
| Healthcheck | `/health/ready` | `/healthz` |
| Timeout | 300 s | 300 s |
| Replicas | 1 | 1 |
| Volumes | none (`volumeMounts: []`) | none |
| Restart policy | `ON_FAILURE` | `ON_FAILURE` |
| Trigger branch | `main` | `main` |
| Wait for CI | enabled | enabled |
| Pre-deploy | `alembic upgrade head` | none |

Architecture matches the intended layout: single replica per service, API
gated on schema-aware readiness, frontend on `/healthz`, and attachments
disabled so the single-replica local-storage constraint is not a live risk.
No replica, service, volume, port, or variable was changed in this session.

---

## 6. Additional changes (CI maintenance)

### Applied by the merge under review

None beyond the already-merged PR #19. This session changed no application or
deployment code.

### New maintenance PR — Node.js 24 action runtimes

| Item | Value |
| --- | --- |
| Branch | `chore/ci-node24-actions` (created from `origin/main` = `2ca6930`) |
| PR | [#20](https://github.com/mdjayedgazi/HelpDesk/pull/20) — **open, not merged** |
| Files changed | `.github/workflows/ci.yml` only (15 lines) |
| Commit | `f2a768b` |

Actions upgraded after checking each upstream release and verifying the full
SHA through the GitHub API:

| Action | Before | After | Runtime |
| --- | --- | --- | --- |
| `actions/checkout` | v4.2.2 | v7.0.1 (`3d3c42e5…`) | node24 |
| `actions/setup-node` | v4.4.0 | v7.1.0 (`949feb24…`) | node24 |
| `astral-sh/setup-uv` | v6.6.1 | v10.4.0 (`1db35dd8…`) | node24 |
| `azure/setup-helm` | v4.3.1 | v5.1.0 (`2f5e7bc6…`) | node24 |
| `gitleaks/gitleaks-action` | v2.3.9 | v3.0.0 (`e0c47f4f…`) | node24 |

Compatibility: every input the workflow uses still exists with the same meaning;
gitleaks v3 is documented as a runtime-only change; `setup-uv` v10 only changes
auto-caching for `pull_request_target`/`workflow_run`/`release`, none of which
this workflow uses (it sets `enable-cache: true` explicitly). Full SHA pinning
and least-privilege permissions preserved.

Verification of PR #20 (run `44903939674`):

```
All 8 jobs: success
Docker job: Trivy backend + frontend scans, SARIF validation, and both
            uploads all success
Security job: gitleaks, CodeQL init/autobuild/analyze all success
Node.js 20 warnings: 0  (post-merge run had 8)
actionlint: clean; YAML: valid
Local: Ruff, format, Pyrefly 0 errors, 456 backend tests (47 skips);
       frontend typecheck, lint, 52 tests, production build
```

PR #20 is left open for review and was **not** merged automatically.

---

## 7. External prerequisites (rechecked, read-only)

| Area | Current observed state | Status |
| --- | --- | --- |
| **Neon PITR / backups** | Not observable without the Neon console; no PITR window or retention confirmed; no restore drill performed | **UNRESOLVED** |
| **Clerk** | API key `sk_test_*`, web key `pk_test_*` (decodes to `social-ferret-6540.clerk.accounts.dev`), profile `college-demo` | **UNRESOLVED for customers** (valid for demo) |
| **OWNER** | Only one user, role `CUSTOMER`; `INITIAL_ADMIN_EMAIL` not set on the API | **UNRESOLVED** — no OWNER; nothing promoted |
| **Upstash Redis** | `rediss://` TLS, `PING` → `PONG`, 8.4.0, 0 keys, 64 MB, policy `optimistic-volatile`; ownership/expiry/durability not observable | **PARTIALLY VERIFIED** |
| **Object storage** | None; `ATTACHMENTS_ENABLED=false`; single replica | **UNRESOLVED / by design** |
| **Interactive authenticated flow** | No authorized test account; not exercised | **UNVERIFIED** |

No credential was displayed, no key rotated, no OWNER promoted, no Redis flush,
and no storage provider changed.

Note on the Clerk key: a Clerk publishable key is public by design and is
embedded in any browser bundle. It was confirmed only by family prefix and by
the instance host it encodes, not by printing the secret key.

---

## 8. Final conclusion

### Deployment

**DEPLOYMENT VERIFIED** for the college-demo environment:

- Both `helpdesk-api` and `helpdesk-web` are `SUCCESS` on the merge commit
  `2ca6930`, which is the current `main`.
- The Railway pre-deploy ran `alembic upgrade head` and moved Neon from `0009`
  to `0011`; the new column and all three indexes exist, and existing data was
  preserved.
- Build logs show the Docker image built and `/health/ready` passed before the
  new container served traffic.
- Live smoke tests pass: 200 liveness/readiness, 401 on protected endpoints,
  404 on unknown, frontend routes and assets 200, missing asset 404, security
  headers and CSP present, and the previously broken CORS preflight now returns
  200 with `Idempotency-Key` allowed while a foreign origin is still rejected.

### Application readiness

**COLLEGE-DEMO READY.** The deployed release is functioning end to end for the
intended public demo: correct code, migrated schema, healthy services, working
CORS, and a green post-merge pipeline.

It is **not** CUSTOMER-PRODUCTION READY. The known external blockers remain:
Neon PITR and a tested restore, a production Clerk instance, Upstash durability
and ownership confirmation, an OWNER account, object storage before any
scale-out, and an interactive authenticated test with a real session. None of
these were resolved in this session, and this report does not claim otherwise.
