# Production release runbook

This is the checklist for promoting HelpDesk from the verified demo scope to a
controlled staging environment and then a real-customer production deployment.
It distinguishes what is **done in the repository**, what is **verified here**,
what requires **operator action** in an external dashboard, and what is
**blocked** without credentials.

Legend: **DONE** · **VERIFIED** · **OPERATOR** (external action required) ·
**BLOCKED** (no access) · **N/A**

> This runbook never contains real credentials. Every secret is referenced by
> variable **name** only and set through the platform's secret UI or
> `railway variable set NAME --stdin --skip-deploys`.

---

## 0. Pre-release gate (all must be true)

| # | Check | Status |
| --- | --- | --- |
| 0.1 | Backend: ruff, format, pyrefly, full pytest green | **DONE / VERIFIED** (see `data.md`) |
| 0.2 | Frontend: typecheck, lint, tests, coverage, build green | **DONE / VERIFIED** |
| 0.3 | PostgreSQL + Redis integration suites green on disposable services | **DONE / VERIFIED** |
| 0.4 | Migrations: single head, `alembic check` clean, downgrade/re-upgrade gate | **DONE / VERIFIED** |
| 0.5 | Docker images build; non-root; Trivy fixable CRITICAL/HIGH = 0 | **DONE / VERIFIED** |
| 0.6 | Browser/responsive matrix green | **DONE / VERIFIED** |
| 0.7 | CI on the release branch green | **OPERATOR** (open the PR checks) |
| 0.8 | At least one independent backup exists and has been restored once | **OPERATOR** (Neon) |

If any of 0.7–0.8 is not true, **do not proceed**.

---

## 1. Clerk production configuration (OPERATOR)

Production must use a Clerk **production** instance, not the demo development
instance. The backend refuses to start outside the demo profile unless
`CLERK_SECRET_KEY` starts with `sk_live_`.

1. **OPERATOR** — Create/own a Clerk production instance for the real domain.
2. **OPERATOR** — In Clerk, add allowed origins / redirect URLs for the exact
   frontend origin (e.g. `https://helpdesk.acme-corp.com`).
3. **OPERATOR** — Set, without pasting into chat/source/logs:
   - Backend (`helpdesk-api`): `CLERK_SECRET_KEY` = `sk_live_…`.
   - Frontend build (`helpdesk-web`): `VITE_CLERK_PUBLISHABLE_KEY` = `pk_live_…`
     (must match the same instance). **The frontend must be rebuilt**, because
     Vite bakes this value into the bundle at build time.
   - Frontend runtime: `CLERK_FAPI_ORIGIN` = the production Frontend API origin
     if it is a custom domain (used in the CSP).
4. **OPERATOR** — Set `DEPLOYMENT_PROFILE=standard` and `ENVIRONMENT=production`
   on the API. Do not keep `college-demo` for commercial use.
5. **VERIFIED after redeploy** — browser loads Clerk from the production FAPI
   origin, no CSP violations; a real sign-in succeeds and redirects to the
   configured origin; the token `azp` matches `FRONTEND_URL`.

### Consistency checks (code-enforced)
- `FRONTEND_URL` and `CORS_ORIGINS` are normalized to exact origins and used for
  both CORS and Clerk `azp` — a trailing slash cannot silently mismatch.
- A development `sk_test_` key is rejected in the `standard` production profile.
- **DONE** — tests assert these.

---

## 2. Owner and initial admin (OPERATOR)

- **DONE** — The code enforces exactly one Owner via a partial unique index, an
  advisory lock, and demote-before-promote ordering. `OWNER_EMAIL` (verified Clerk
  **primary** email only) drives recognition; `INITIAL_ADMIN_EMAIL` is a deprecated
  fallback.
- **DONE** — `python -m app.commands.bootstrap_owner` promotes a single existing
  linked account whose verified primary email matches `OWNER_EMAIL`, refusing if
  an Owner already exists. `python -m app.commands.reconcile_owner` is the
  idempotent, deploy-time variant.
- **OPERATOR** — Confirm an active, correctly linked Owner exists. Recommended,
  non-destructive procedure:
  1. Ensure the intended person has signed in once (so a local account exists).
  2. Set `OWNER_EMAIL` on the API service to their verified Clerk primary email.
  3. Run `python -m app.commands.reconcile_owner --json` from a one-off shell and
     read the reported `status` (e.g. `promoted`/`already_owner`/`target_missing`).
  4. Verify `GET /api/v1/users/me` for that account returns `role: owner`.
- **BLOCKED** — Do **not** promote or change production roles without the owner's
  explicit authorization.

---

## 3. Neon backup confirmation and restore drill (OPERATOR)

Follow [`DATABASE_BACKUP_RESTORE.md`](./DATABASE_BACKUP_RESTORE.md).

- **OPERATOR** — In Neon **Settings → Backups**: record plan, PITR on/off,
  retention window, region, who can restore.
- **OPERATOR** — Take a manual logical backup before the first production
  migration (`pg_dump --format=custom`).
- **OPERATOR** — Perform a **restore drill** into an isolated branch/target (never
  over production) and verify per §4 of that runbook: `alembic_version` equals the
  expected head, `schema_status` prints `ok`, table counts are plausible, and a
  smoke read returns expected data.
- **BLOCKED** — A verified restore requires Neon access; until it is done, treat
  the database as not recoverable and do not accept real-customer data.

Evidence to record (outside the repo): date, source branch/backup, target,
observed counts, `alembic_version`, `schema_status`.

---

## 4. Upstash Redis verification (OPERATOR)

See [`PRODUCTION_READINESS.md`](./PRODUCTION_READINESS.md) §2.

- **DONE** — Code requires TLS in the demo profile, is fail-closed on outage, sets
  connect/socket timeouts, never logs the URL, and reports `redis` in readiness.
- **OPERATOR** — Claim the database (if a temporary no-signup instance), confirm
  plan/region/TLS, review eviction/maxmemory.
- **OPERATOR** — Verify rate limiting after redeploy: rate-limit headers present,
  a deliberate burst returns `429`, and `/health/ready` shows `redis: ok`.
- **DO NOT** run `FLUSHALL`/`FLUSHDB` or rely on Redis for application data.
- **BLOCKED** — Durability/eviction behaviour can only be confirmed in the console.

---

## 5. Attachments and malware scanning (DECISION)

- **DONE** — Uploads are fail-closed: allowlist + magic-byte check, quarantine →
  ClamAV scan → publish only on explicit `CLEAN`; path-safe download; per-ticket
  quotas. Attachments can be fully disabled via `ATTACHMENTS_ENABLED=false`
  (the current demo state).
- **OPERATOR** — To enable uploads, deploy a private clamd service, set
  `MALWARE_SCAN_ENABLED=true` and `CLAMAV_HOST`/`CLAMAV_PORT`, mount a durable
  volume at `UPLOAD_DIR`, then run `python -m app.commands.scan_attachments` once.
- **Constraint** — Local-volume storage means **one backend replica** only. Do not
  scale out until object storage (S3/R2) is implemented and files migrated.
- **BLOCKED** — Object storage is not implemented (no provider access/credentials
  in this change). Keep attachments disabled or keep a single replica + volume.

---

## 6. Railway configuration (OPERATOR)

Verify the **current** dashboard state; do not assume prior settings persist.

| Setting | Backend (`helpdesk-api`) | Frontend (`helpdesk-web`) |
| --- | --- | --- |
| Root directory | `backend/` | `frontend/` |
| Build | `backend/Dockerfile` | `frontend/Dockerfile` |
| Start | image default (uvicorn on `$PORT`) | image default (nginx on 8080) |
| Health check path | `/health/ready` | `/healthz` |
| Health check timeout | generous (≥ 60 s start period) | ≥ 30 s |
| Replicas | **1** while uploads are volume-local | 1 |
| Pre-deploy command | `alembic upgrade head` | — |
| Wait for CI | enabled | enabled |

**Desired release sequence:** CI passes → pre-deploy `alembic upgrade head`
runs and a failure blocks activation → app starts → `/health/ready` confirms
`schema: ok` → Railway routes traffic only when ready → frontend `/healthz` green.

- **OPERATOR** — Confirm each row above in the dashboard.
- **OPERATOR** — Confirm `MIGRATION_DATABASE_URL` (if set) points at the same
  database as `DATABASE_URL`, or unset it, so migrations cannot target a stale DB.
- **BLOCKED** — The pre-deploy command and wait-for-CI toggles are dashboard-only
  and not exposed read-only via the CLI.

---

## 7. Migration verification (OPERATOR)

Before and after deploying:

```bash
alembic current          # must equal the image's expected head
alembic check            # must report no new upgrade operations
alembic history --verbose
```

- **DONE** — The readiness probe compares the live `alembic_version` to the head
  shipped in the image and fails readiness in production on a mismatch.
- **DO NOT** routinely downgrade production. `0001` drops all tables; migrations
  are not a data-preserving rollback. Prefer a forward fix and an app rollback.

---

## 8. Health checks and security headers (OPERATOR + VERIFIED)

- **VERIFIED (this pass)** — Live demo API returns `200` from `/health/live` and
  `/health/ready` (`database: ok`, `schema: ok`, `redis: ok`, `clamav: disabled`);
  unauthenticated `/api/v1/users/me` returns `401`; CORS preflight is allowed only
  from the configured origin.
- **VERIFIED (this pass)** — Live web returns `200` `/healthz`, SPA fallback works,
  and CSP + `X-Frame-Options: DENY` + `nosniff` + `Referrer-Policy` +
  `Permissions-Policy` are present.
- **DONE (this pass)** — HSTS `includeSubDomains` is now **opt-in**
  (`HSTS_INCLUDE_SUBDOMAINS`, default `false`); enabling HSTS emits
  `max-age` only unless subdomain readiness is confirmed. Covered by tests.
- **OPERATOR** — Only after verified HTTPS on both domains, set `HSTS_ENABLED=true`
  (and `HSTS_INCLUDE_SUBDOMAINS=true` only when all subdomains are HTTPS). Do not
  use `preload` without a deliberate review.

---

## 9. Monitoring (OPERATOR)

See [`MONITORING_AND_ALERTING.md`](./MONITORING_AND_ALERTING.md).

- **OPERATOR** — Wire an external uptime probe to `/health/ready` (API) and
  `/healthz` (web); route to on-call.
- **OPERATOR** — Enable Railway/Neon/Upstash alerts for deployment failure,
  DB connections/storage/backups, and Redis availability.
- **OPERATOR** — Name an on-call owner and escalation path.
- **BLOCKED** — No alerting is configured by the repository; it cannot be.

---

## 10. Rollback strategy

1. **Application rollback:** redeploy the previous known-good image tag in
   Railway (both services as needed). This is the primary, safest rollback.
2. **Database:** prefer a **forward fix**. Never run a destructive downgrade on
   production. If data is corrupted, restore to a **new** verified database and
   repoint `DATABASE_URL` (and `MIGRATION_DATABASE_URL`) — see
   `DATABASE_BACKUP_RESTORE.md` §5.
3. **Frontend:** the publishable key and API origin are baked in; a rollback is a
   redeploy of the previous frontend build, not just a restart.
4. **Feature toggles:** attachments can be disabled at any time with
   `ATTACHMENTS_ENABLED=false` without a schema change.

---

## 11. Post-deployment verification

- `GET /health/ready` → `200` with `database: ok`, `schema: ok`.
- `GET /healthz` (web) → `200`; SPA routes render.
- Real sign-in works against the production Clerk instance; role-based navigation
  is correct for a customer, agent, admin, and owner.
- A ticket can be created by a customer and is visible to staff; staff can update
  status; notifications appear.
- Security headers present; HSTS only if intentionally enabled.
- No new 5xx spike after traffic is routed.
- Record the deployed image digests/commits and the timestamp.

---

## 12. Sign-off

| Decision | Meaning |
| --- | --- |
| CODE QUALITY | Passes all engineering and security gates (see `data.md`). |
| STAGING READY | Set when §1, §3, §4, §6, §7, §9 are done at least once in a controlled staging environment. |
| PRODUCTION READY | Set only when all of the above plus a verified restore drill, production Clerk sign-in, monitoring, and attachment-storage decisions are complete. |

Do not mark PRODUCTION READY on CI green alone.
