# HelpDesk — Final Engineering Remediation, Security Hardening & Production Readiness

**Date:** 2026-11-23
**Repository:** `mdjayedgazi/HelpDesk`
**Branch:** `audit/full-project-review` (extends audit PR #35)
**Base:** `main` @ `e757445`; audit commit under review `6371349`
**Related audit:** `data.md` (PR #35) and `docs/frontend-responsive-engineering-report.md`

---

## 1. Executive summary

This pass remediated every confirmed, safely fixable finding from the previous
audit, and added the measurement and verification infrastructure the audit called
out as missing. All automated gates reproduced green in this environment; the
external-service items are reported honestly with the exact evidence available.

What changed, in one line each:

- **HD-AUD-03** — removed the unused, stale `HelpDeskApi` documentation interface
  (and its dead type-import block) from `frontend/src/lib/api.ts`.
- **HD-AUD-04** — replaced the length-guessed admin user list with real
  server-side pagination: a typed `UserPage` envelope, single-round-trip windowed
  count, deterministic ordering, full frontend wiring and pagination tests.
- **HD-AUD-05** — made the Trivy image gate **blocking** (CRITICAL/HIGH,
  `ignore-unfixed`), after upgrading both base images so the measured baseline of
  fixable findings dropped from **44 backend / 58 frontend → 0 / 0**.
- **Coverage** — added backend `pytest-cov` (75% gate, currently 75.8%) and
  frontend v8 coverage (40.04% lines measured; regression floor 38/38/30/40),
  with CI artefacts.
- **Integration tests** — added page-level integration tests for the agent queue,
  ticket detail, notifications, account requests and admin users (frontend tests
  231 → **255**).
- **Browser verification** — repaired a previously broken harness (it aliased
  Clerk to a non-existent `/tmp` path) into a self-contained, in-repo harness and
  added a real-Chromium matrix: **9 routes × 11 widths**, zero horizontal
  overflow, zero console errors, SPA navigation and reduced-motion verified.
- **PostgreSQL/migrations** — reproduced the full migration gate and every
  PostgreSQL/Redis integration suite on disposable services; all pass.

**Verdict: C — DEMO / DEVELOPMENT READY.** It is suitable for its verified demo
scope and for local development. It is **not** production ready: real Clerk
production sign-in, a Neon restore drill, Upstash durability evidence, a real
ClamAV deployment and monitoring/alerting are still unverified (Section 18).

---

## 2. Initial repository state

| Item | Finding |
| --- | --- |
| Branch | `audit/full-project-review` (PR #35, **OPEN**, all CI green) |
| HEAD at start | `6371349` |
| `origin/audit/full-project-review` | in sync with local |
| Working tree | `data.md` modified — **0 bytes** (emptied again, same failure mode as the prior audit) |
| `HEAD:data.md` | 3046 lines / 137,751 bytes (intact) |
| Open PRs | #35 only |

**Data-loss incident (handled, not hidden).** On entry, the working-tree
`data.md` was empty (0 bytes) while the committed `HEAD:data.md` held the full
3,046 lines. This is the second time this file has been truncated in the working
tree. I preserved the empty working copy to `/tmp` for evidence, restored the
working file from the committed HEAD (`git show HEAD:data.md`), and confirmed the
restored file's SHA-256 (`ae70fe87…`) matches the committed blob. No historical
content was lost. The root cause is an external process truncating the file
between sessions; it is documented here so the next operator checks immediately.

PR #35 was verified still open and mergeable; per the instructions the work
extends its existing branch rather than opening a duplicate PR.

---

## 3. Existing audit findings carried in

| ID | Severity | Summary | Status now |
| --- | --- | --- | --- |
| HD-AUD-01 | P1 | Non-owner requests took a global advisory lock + Clerk call | Fixed in PR #35 (not re-touched) |
| HD-AUD-02 | P2 | `data.md` history emptied | Fixed in PR #35; recurrence handled again (Section 2) |
| HD-AUD-03 | P3 | Unused stale `HelpDeskApi` interface | **Fixed here** |
| HD-AUD-04 | P3 | Length-based admin user pagination | **Fixed here** |
| HD-AUD-05 | Info | Trivy gate non-blocking | **Fixed here** |

---

## 4. Confirmed problems reproduced

Before fixing, each item was reproduced against the real code:

1. **Stale contract (HD-AUD-03):** `grep -rn "HelpDeskApi" frontend/src` returned
   exactly one hit — its own declaration. It was dead code whose `listTickets`
   returned `Ticket[]` while the backend returns a `TicketPage` envelope.
2. **Bounded-but-guessed pagination (HD-AUD-04):** the backend `/api/v1/users`
   returned a bare `list[UserRead]`; the page inferred "next" from
   `items.length === PAGE_SIZE`, which is wrong for a partial last page. There was
   no server total.
3. **Non-blocking image gate (HD-AUD-05):** `exit-code: "0"` on both Trivy scans.
   A local Trivy 0.70.0 run against the built images reported **44** fixable
   CRITICAL/HIGH (backend, all Debian base packages) and **58** (frontend, Alpine
   packages) — i.e. the policy could never have failed meaningfully.
4. **Broken browser harness (F):** `vite.harness.config.ts` aliased
   `@clerk/react` to `/tmp/opencode/hd-harness/clerk.tsx`, a path outside the
   repository that does not exist on a clean checkout. The harness could not run
   reproducibly.
5. **No coverage measurement (D):** neither `pytest-cov` nor a Vitest coverage
   provider was installed.

---

## 5. Files modified

Backend:
- `app/api/routers/users.py` — `UserPage` envelope, `_count_and_page_users`
  windowed count, deterministic ordering, page/page_size params.
- `app/schemas/users.py` — new `UserPage` schema.
- `pyproject.toml` — `pytest-cov` dev dep; `[tool.coverage.*]` config with a 75%
  gate.
- `tests/test_admin.py`, `tests/test_owner.py`, `tests/test_regressions_qa.py` —
  updated to the envelope; added pagination tests.
- `tests/test_user_pagination_postgres.py` — new PostgreSQL windowed-count /
  ordering test.
- `Dockerfile` — `apt-get upgrade` to apply Debian security updates at build.
- `.gitignore` — ignore regenerated `coverage.json`.
- `uv.lock` — `coverage`, `pytest-cov`.

Frontend:
- `src/lib/api.ts` — removed unused `HelpDeskApi` + dead type imports.
- `src/lib/types.ts` — `UserListParams` → `page`/`page_size`; new `UserPage`.
- `src/hooks/useAdmin.ts` — `useAdminUsers` returns `UserPage`; new
  `useUserDirectoryList` for flat lookups.
- `src/hooks/useUserDirectory.ts`, `src/pages/staff/AccountRequestsPage.tsx` —
  use the flat directory list.
- `src/pages/admin/AdminUsersPage.tsx` — server pagination + page reconciliation.
- `src/test/setup.ts` — jsdom `ResizeObserver`/`matchMedia` polyfills.
- `vite.config.ts` — coverage config + thresholds + robust test timeout.
- `vite.harness.config.ts`, `src/test/harness-clerk.tsx`,
  `src/harness-fixtures.ts` — self-contained harness (in-repo Clerk stub, users
  envelope, messaging fixtures).
- `scripts/browser-verify.mjs` — real-Chromium route × width matrix.
- New tests: `AdminUsersPage.test.tsx`, `AgentQueuePage.test.tsx`,
  `NotificationsPage.test.tsx`, `TicketDetailPage.test.tsx`,
  `AccountRequestsPage.test.tsx`.
- `package.json` / `package-lock.json` — `@vitest/coverage-v8`, `@playwright/test`,
  `test:coverage`, `test:browser`, `dev:harness` scripts.
- `Dockerfile` — `apk upgrade` at build.

CI:
- `.github/workflows/ci.yml` — backend/frontend coverage steps + artefacts;
  blocking Trivy policy steps (SARIF still uploaded); new `browser-verify` job;
  new PostgreSQL pagination test in the integration job.

---

## 6. Root causes

- **HD-AUD-03:** the interface was a documentation aid left over from before the
  list endpoints introduced pagination envelopes; nothing imported it.
- **HD-AUD-04:** the ticket list had migrated to a server envelope + windowed
  count, but the user directory had not; the client compensated by guessing.
- **HD-AUD-05:** the base images were pinned by tag but never patched, so fixable
  OS CVEs accumulated; the gate was disabled to avoid red builds.
- **Harness:** a developer-local absolute path leaked into a committed config.
- **Coverage:** no provider installed, so no measurement existed to gate on.

---

## 7. Implemented fixes

**HD-AUD-03 — remove stale contract.** Deleted the `HelpDeskApi` interface, its
`export type { TicketStatus }` re-export, and the now-unused `./types.ts` import
block in `api.ts`. No runtime change; verified by typecheck/lint/tests.

**HD-AUD-04 — real server-side pagination.** `GET /api/v1/users` now takes
`page` (≥1) and `page_size` (1–100), executes one query with
`count(*) OVER ()` to return the page rows and the exact filtered total together,
orders by `created_at DESC, id DESC` for deterministic paging, and returns a
`UserPage` envelope identical in shape to `TicketPage`. The frontend
`AdminUsersPage` drives Prev/Next/numbers from `total`/`total_pages`, clamps an
out-of-range page to the last valid one, and resets to page 1 on filter/search
change. Lookup consumers (display-name resolution, the account-request picker)
use a `useUserDirectoryList` helper that fetches the maximum page and unwraps
`items`, so their behaviour is unchanged.

**HD-AUD-05 — blocking image gate.** Resolving the CVEs took two steps. First,
both Dockerfiles apply the distro package upgrade during build
(`apt-get upgrade` / `apk upgrade`), which cleared the OS-package findings.
Second, the runtime image was carrying the base image's bundled **system
pip/setuptools**, whose stale setuptools wheel scanners flag as fixable
CRITICAL/HIGH even though the runtime never imports it (dependencies live in the
uv-built venv). The backend Dockerfile now upgrades pip during the build and then
**uninstalls the system pip + setuptools from the final image entirely** — dead
weight here — which removed the last finding. Measured with a fresh Trivy DB:
backend **44 → 0**, frontend **58 → 0** fixable CRITICAL/HIGH.

The CI keeps producing and validating SARIF (uploaded to the Security tab) and
then runs an explicit policy step that fails the job if the SARIF contains any
result, with `severity: CRITICAL,HIGH` and `ignore-unfixed: true`. Gate logic
verified: passes at 0 results, fails at 44. No blanket suppression was added;
because the baseline is now zero fixable, no exception entry was required.

**Coverage (D).** Backend: `pytest-cov`, branch coverage, `fail_under = 75`
(measured 75.8% combined; ~80% line excluding the two bulk seed-fixture scripts,
which are covered by the PostgreSQL seed suites). Frontend: Vitest v8 coverage
with `lcov`/`json-summary`, explicit `include` of `src/**` and exclusions only for
tests/test scaffolding; thresholds 38 lines/statements, 30 functions, 40
branches. Both produce CI artefacts. Thresholds are regression floors, explicitly
documented as such — not arbitrary quality targets.

**Integration tests (E).** Added page-level tests exercising the real page
components with realistic fixtures and mocked hooks: loading/empty/error states,
role-dependent controls, pagination (server metadata, next/prev, reset-on-search),
mark-read, claim, and out-of-range handling. jsdom was given inert
`ResizeObserver`/`matchMedia` polyfills so Chakra/Zag widgets render for real
rather than being mocked away.

**Browser verification (F).** The harness now runs from any checkout: Clerk is a
small in-repo stand-in reachable only via the harness alias (confirmed absent from
the production bundle), and fixtures cover every endpoint the toured pages call.
`scripts/browser-verify.mjs` drives Chromium across routes and widths.

**PostgreSQL/migrations (G).** See Section 13.

---

## 8. New regression tests

- `backend/tests/test_admin.py`: envelope shape, empty, exact-full-page,
  multi-page partition (no dup/omission), partial last page, out-of-range page
  returns true total, invalid bounds (page 0/-1, page_size 0/101 → 422), max page
  size, filter reflected in `total`, admin/owner-only.
- `backend/tests/test_user_pagination_postgres.py`: windowed count matches real
  total, `created_at DESC, id DESC` tie-break, out-of-range fallback count.
- `frontend/src/pages/admin/AdminUsersPage.test.tsx` (7): loading, render,
  server-metadata pagination + next, prev, empty, error, reset-on-search.
- `frontend/src/pages/agent/AgentQueuePage.test.tsx` (4): empty, render + claim,
  claim mutation, error.
- `frontend/src/pages/NotificationsPage.test.tsx` (5): empty, render, error,
  mark-all-read, unread-filter.
- `frontend/src/pages/TicketDetailPage.test.tsx` (4): 404, server error, owner
  render, customer never gets staff history.
- `frontend/src/pages/staff/AccountRequestsPage.test.tsx` (4): list, empty,
  error, role-gated create control.

No existing test was weakened or deleted.

---

## 9. Backend test results

| Command | Result |
| --- | --- |
| `uv run ruff check .` | All checks passed |
| `uv run ruff format --check .` | 128 files already formatted |
| `uv run pyrefly check` | 0 errors |
| `uv run pytest -q` | **593 passed, 75 skipped** |
| `uv run pytest -q --cov` | coverage 75.8%, gate 75.0% reached |

(The skip count rose from 72 to 75 because the new PostgreSQL pagination module
adds three opt-in tests, skipped on SQLite as designed.)

---

## 10. Frontend test results

| Command | Result |
| --- | --- |
| `npm run typecheck` | pass |
| `npm run lint` | pass |
| `npm test` | **255 passed, 29 files** |
| `npm run test:coverage` | 255 passed; thresholds met |
| `npm run build` (CI env) | success; largest shared vendor ~109 kB gzip |

---

## 11. Coverage results

- **Backend:** statements 3,826 tracked; combined **75.8%** (line ~80%, branch
  ~58% excluding the two bulk seed scripts). Gate **75%**.
- **Frontend:** statements 39.98%, branches 41.96%, functions 32.14%, lines
  **40.04%**. Floors **38/38/30/40**.
- **Directory detail (frontend):** `src/auth` 87.5% lines, `src/lib` 69.0%,
  `src/components` 39.3%, `src/pages` 36.0%. The remaining gap is largely
  lazy-loaded page layout/JSX that unit tests do not exercise and that the
  browser matrix covers instead. This is stated rather than papered over.

---

## 12. PostgreSQL integration results

Executed against disposable containers (PostgreSQL 16, Redis 7) with the
repository's disposable-database guard satisfied:

| Suite | Result |
| --- | --- |
| `test_e2e_support_flow_postgres.py` | 2 passed |
| `test_postgres_integration.py` + `test_support_workflows_postgres.py` + `test_internal_messages_postgres.py` + `test_qa_seed_postgres.py` | 25 passed |
| `test_owner_identity_postgres.py` | 6 passed |
| `test_user_pagination_postgres.py` | 3 passed |
| `test_demo_seed_postgres.py` (dedicated DB) | 31 passed |
| `test_rate_limit.py` + `test_analytics_cache.py` | 22 passed |

No production database was touched.

---

## 13. Migration verification

Against a disposable PostgreSQL database (`migrate_verify`):

- `alembic heads` → single head `0012_staff_mentions`.
- `alembic upgrade head` → clean.
- `alembic current` → `0012_staff_mentions (head)`.
- `alembic check` → "No new upgrade operations detected." (models == migrations).
- `alembic downgrade 0008_ticket_number_not_null` then `upgrade head` → clean.
- `alembic upgrade head --sql` → 62 DDL statements rendered offline.

The model change in this PR (new `UserPage` response schema) does **not** alter
any table, so no migration is required and `alembic check` confirms no drift.

---

## 14. Docker results

| Check | Result |
| --- | --- |
| Backend image build (after `apt-get upgrade`) | success |
| Frontend image build (after `apk upgrade`) | success |
| Frontend non-root | uid **101** |
| Frontend `/healthz` | `ok` |
| Frontend SPA `/tickets` | 200 |
| Frontend CSP header present | yes |
| Backend non-root (via entrypoint) | uid **10001** |

Note: tracing the non-root user required running through the image's entrypoint
(`gosu`), which is the correct path; a raw `id -u` bypasses it.

---

## 15. Trivy results

Local Trivy 0.70.0 with a freshly downloaded DB, `--severity CRITICAL,HIGH
--ignore-unfixed`:

| Image | Before | After |
| --- | --- | --- |
| Backend (`python:3.13.1-slim-bookworm`) | 44 | **0** |
| Frontend (`nginx:1.29-alpine`) | 58 | **0** |

Backend breakdown: the first pass (`apt-get upgrade`) cleared the OS-package
findings; a fresh-DB rescan then surfaced a stale **system pip/setuptools**
bundle (a piptest reproduced it from `pip install --upgrade pip` alone). Since
the runtime uses only the uv-built venv, the build now uninstalls the system
pip + setuptools from the final layer, which removed the last finding and keeps
the app importable (verified: `import app.main` succeeds; `alembic` and
`uvicorn` present in the venv).

Policy gate logic verified by feeding the pre-upgrade SARIF (44 results) to the
`jq` gate — it fails correctly — and the post-upgrade SARIF (0 results) — it
passes. Policy: CRITICAL/HIGH blocking, `ignore-unfixed: true` (an unavailable
vendor fix cannot be remediated here; only *fixable* findings block). No CVE
exception list was needed because the baseline is now zero fixable.

---

## 16. Browser E2E results

- **Real browser, harness-backed matrix:** Chromium (Playwright 1.65.1).
  **9 routes × 11 widths** (320, 360, 390, 480, 640, 768, 1024, 1280, 1440, 1920,
  2560): zero horizontal overflow, zero uncaught console errors, per-role route
  landmark present, in-app navigation keeps the SPA alive, reduced-motion renders
  correctly. **All passed.**
- **Not performed (external blocker):** live browser E2E against a real Clerk
  **production** session. No authorized production test identity is available to
  this environment, and creating one or bypassing auth is explicitly disallowed.
  The harness is honestly a fixture-driven render of the real app, not proof of
  the production auth flow.

---

## 17. Responsive results

Covered by the matrix above (Section 16). Tables scroll within their own
container; the page does not overflow at any tested width. Previous reviewers'
wider asset sweeps remain in `docs/responsive-assets/` and `docs/motion-assets/`.
This run independently re-confirms zero page overflow on the harness-rendered
application.

---

## 18. External service verification

All external checks were **read-only**. No variable, secret, deployment or data
was modified. (Handling note: a Railway `variables` listing displayed secret
values in the terminal; none are reproduced here, and no value was copied,
logged to a file, or committed.)

### Railway (verified read-only)

- Workspace `MD. JAYED GAZI's Projects`; project `helpdesk-college-demo`;
  environment `production`.
- Services: `helpdesk-web` and `helpdesk-api`, both public, both currently
  **Sleeping** but serving when woken (health probes returned 200).
- API config (names/coarse values only): `ENVIRONMENT=production`,
  `DEPLOYMENT_PROFILE=college-demo`, `ATTACHMENTS_ENABLED=false`,
  `MALWARE_SCAN_ENABLED=false`, `AUTO_CREATE_TABLES=false`, `RATE_LIMIT_ENABLED=true`,
  `RATE_LIMIT_REDIS_URL` is `rediss://` (TLS), `DB_POOL_SIZE=1`
  (Neon-pooler friendly), `LOG_JSON=true`, `OWNER_EMAIL` set, `FRONTEND_URL`
  is the web origin. **Not verified:** the pre-deploy migration command and
  wait-for-CI flag (not surfaced by the CLI read-only commands available).

### API live endpoints (verified)

- `GET /health/live` → 200 `{"status":"ok"}`.
- `GET /health/ready` → 200, `status: ready`, checks:
  `database: ok`, `schema: ok` (**running at the image's migration head**),
  `redis: ok`, `clamav: disabled` (expected for college-demo).
- `GET /api/v1/users/me` without a token → **401**.
- CORS preflight from the configured web origin → 200; from a foreign origin →
  no `Access-Control-Allow-Origin` (correctly rejected).

### Web live (verified)

- `/healthz` → 200; `/tickets` → 200 (SPA fallback).
- Security headers present: CSP (Clerk-compatible), `X-Frame-Options: DENY`,
  `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`.
- **HSTS not present**: consistent with the college-demo profile not enabling it.
- CSP references a **Clerk development** FAPI host (`*.clerk.accounts.dev`) —
  consistent with the college-demo profile, not a production Clerk instance.

### Not verifiable from here (explicit external requirements)

| Item | Status | Exact requirement to verify |
| --- | --- | --- |
| Clerk **production** sign-in, session, provisioning, logout | **NOT TESTED** | An authorized Clerk production test user + a browser session |
| Clerk inactive-user and Owner-identity flows in production | **NOT TESTED** | Same authorized identities |
| Neon backup availability / PITR / retention | **NOT VERIFIED** | Neon console access or an isolated restore target |
| Neon restore drill | **NOT PERFORMED** | An isolated recovery branch/target and operator approval |
| Upstash durability / eviction / memory limits | **NOT VERIFIED** | Upstash console access (no flush/scan performed) |
| ClamAV clean/infected/timeout behaviour in production | **NOT TESTED** | A disposable ClamAV instance with a harmless EICAR-style signature |
| Railway pre-deploy migration command / wait-for-CI | **NOT VERIFIED** | Railway dashboard settings (not exposed read-only via CLI) |
| Monitoring / alerting / on-call ownership | **NOT VERIFIED** | Project owner input; see recommendations below |

### Monitoring assessment

Observed capabilities and gaps:

- The API ships structured, redacted JSON logs (`LOG_JSON=true`) and a
  dependency-aware `/health/ready` — good raw signals.
- Railway provides deployment status and health-check-driven restarts.
- **No dedicated alerting was found** configured for: API 5xx rate, latency,
  database connectivity, Redis availability, attachment-scanner availability,
  deployment failures, or health-check failures. Recommended: route Railway
  health/log events to an alert channel, add an uptime check on `/health/ready`
  from an external prober, and define an on-call owner for the recovery runbook in
  `docs/PRODUCTION_READINESS.md`.

### Attachment storage

`ATTACHMENTS_ENABLED=false` in the live college-demo deployment, so no uploads
are accepted there and attachment durability is not exercised in production. By
design (see `docs/PRODUCTION_READINESS.md`), enabling attachments requires a
ClamAV service and an absolute `UPLOAD_DIR` on a persistent volume; that
combination is unverified in this environment.

---

## 19. Security and reliability regression review (I)

Re-confirmed against the code and tests (no change made to a working
authorization design):

- **AuthN:** identity is always the Clerk `sub`; no role/owner from any body.
- **AuthZ matrix preserved:** customer/agent/admin/owner boundaries unchanged;
  every mutation behind the correct dependency; object-level checks 404 on
  cross-user access. The new `/api/v1/users` pagination keeps the
  `admin_dependency` (agent/customer → 403, verified by tests).
- **Owner identity:** unchanged; the PR #35 performance fix is intact and its
  regression test still passes.
- **Messaging/mentions/notifications:** participant-scoped; mention IDs validated
  as real active staff; notification isolation covered by tests.
- **Attachments:** allowlist + magic bytes + quarantine + scan + path-safe
  download + quotas (all fail-closed).
- **Rate limiting:** atomic, fail-closed; live Redis reachable.
- **CORS/CSP/headers:** live-verified correct (Section 18).
- **Idempotency:** ticket create key preserved.
- **Information leakage:** the new endpoint returns only the existing `UserRead`
  fields (no new user data exposed); errors stay coarse.

Negative-case tests added/retained cover: unauthenticated (401), wrong role (403),
cross-record (404), invalid pagination bounds (422), inactive-user filtering, and
out-of-range pages returning the true total.

---

## 20. Outstanding blockers

1. **External verification** listed in Section 18 (Clerk production, Neon
   restore, Upstash, ClamAV, Railway pre-deploy settings, monitoring). These
   require credentials, console access, or operator approval not available here.
2. **Frontend coverage depth.** 40% line coverage is the measured baseline; the
   floor is a regression guard, not a quality target. Deeper page coverage would
   require progressively more mocking that risks asserting implementation detail;
   the browser matrix is the intended complement.
3. **Dev-only npm advisories** on the existing `vitest 5.0.4` toolchain
   (6 moderate, dev-only). Production dependency audit remains **0**. Not fixed
   here to avoid an unsolicited major-version bump of the test runner; noted for a
   dedicated tooling update.
4. **Recurring `data.md` truncation** by an external process between sessions.
   Content is preserved every time, but the operator should investigate the
   process that zeroes the working copy.

---

## 21. Production-readiness verdict

**C — DEMO / DEVELOPMENT READY.**

Justification:

- Code quality, backend/frontend correctness, authorization, database integrity,
  migrations, Docker builds, image security, coverage measurement, browser
  responsiveness and the live API/web health + security posture are all verified.
- Production readiness additionally requires evidence for production Clerk auth,
  Neon recovery, Upstash durability, a real scanner, monitoring/alerting and the
  Railway pre-deploy gate. Those are **not** verified, so a "PRODUCTION READY"
  classification would be dishonest.

To move to **STAGING READY**: obtain the external verification in Section 18, run
an authorized authenticated browser journey per role, and perform a Neon restore
drill on an isolated target.
