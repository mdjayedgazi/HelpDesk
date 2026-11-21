# HelpDesk — Demo Dataset Generation, Database Seeding & Workspace Verification

**Review date:** 2026-11-21
**Repository:** `mdjayedgazi/HelpDesk`
**Branch:** `feat/demo-dataset-seeding` (new, from `main` @ `69045ff`)
**Companion documents:** [`docs/demo-data-audit.md`](docs/demo-data-audit.md),
[`docs/demo-data-seeding.md`](docs/demo-data-seeding.md),
[`docs/demo-data-seed-report.md`](docs/demo-data-seed-report.md)
**Verdict:** The demo dataset is built, validated end-to-end on a disposable
PostgreSQL 16, and safe to run against production **after** the operator gates
in Part L. No production write was performed by this pass.

> **Document preservation.** `main`'s `data.md` held the PR #19
> production-readiness review. This pass appends its own review above that
> document rather than replacing it; the original is reproduced verbatim from
> Part Z onward.

---

## Part A — Git and PR state at the start

| Item | Finding |
| --- | --- |
| `main` HEAD | `69045ff` — merge of PR #24 |
| PR #22, #23, #24 | all **MERGED** |
| Open PRs | none |
| Working tree | `data.md` had been emptied locally; restored from `HEAD` and then extended with this review |
| New branch | `feat/demo-dataset-seeding` |

No existing PR was modified. No deployment was triggered. No Railway
configuration or environment variable was changed.

---

## Part B — The most important audit finding: a seeder already existed

The repository already contained a **2,179-line, reviewed demo seeder** at
`backend/app/commands/seed_demo_data.py`, plus a separate loopback-only
`seed_qa_data.py`. This changed the job from "write a seeder" to "make the
existing, hardened seeder meet the brief without weakening its guarantees".

What it already did well, and was preserved untouched:

- INSERT-only (no `DROP`/`TRUNCATE`/`DELETE`), atomic, rollback on failure;
- deterministic `uuid5` ids, so re-runs are idempotent;
- refuses loopback hosts and QA-named databases;
- requires an exact confirmation token that names the host and database;
- refuses a declared production environment;
- refuses upload directories outside `/tmp`;
- hashes the Owner row before/after and rolls back on any drift;
- never writes a `clerk_id`.

### B1. The defect that made the dashboard useless

`_BASE = datetime(2026, 8, 15, …)` anchored every timestamp to a fixed past date.
The analytics endpoint derives its 14-day window from `datetime.now(UTC)`, so
**all 120 tickets fell outside the window**:

```
seeded ticket range 2026-08-15 → 2026-08-18
analytics window    2026-11-08 → 2026-11-21
```

Consequence: status/priority/category charts would be correct, but the *Ticket
volume* trend and its sparkline would render **a flat zero line**, and the
"created today / yesterday / last 14 days" scenarios were impossible.

**Fixed** by anchoring to `datetime.now(UTC)` at run time, with a fixed RNG seed
to keep the shape deterministic. Verified: all 14 window days now carry activity
(108 created, 49 resolved).

### B2. Requirement gaps closed

| Brief | Before | Now |
| --- | --- | --- |
| `--size 50/100` | fixed at 100 | implemented, exact splits |
| `--dry-run` | absent | implemented, writes nothing |
| ~300 tickets at 100 | 120 | 300 |
| 60/60/60/90/30 status | modular blend | exact |
| 45/135/90/30 priority | modular blend | exact |
| 14-day trend populated | **empty** | all 14 days |
| 15–20% unassigned active | ≈14% blended | 17% of active |
| realistic aging | all-or-nothing | 24 aging tickets |
| ~600–900 comments | ~650 | 789 |
| ~300–500 notifications | ~? | 525–587 |
| 2 owners | — | **impossible (schema)** |

---

## Part C — Schema and authorization (verified, not assumed)

Ten tables: `users`, `tickets`, `comments`, `notifications`, `ticket_history`,
`attachments`, `staff_conversations`, `staff_messages`, `internal_messages` (+
recipients), `account_management_requests` (+ comments/events), `ticket_feedback`.
Full column/constraint inventory is in `docs/demo-data-audit.md` §3.

Authorization: `CUSTOMER` sees only its own tickets and public comments;
`AGENT` works assigned/unassigned tickets and may author internal notes;
`ADMIN` sees all tickets, analytics and the directory; `OWNER` adds role/status
management. The backend re-checks the local role on every request. Seed data only
*satisfies* these rules — it never bypasses them.

### C1. The 2-owner request is blocked by the schema

`uq_users_single_owner` is a **partial unique index** (`ON users (role) WHERE
role = 'OWNER'`). The application's entire ownership model — and
`bootstrap_owner`'s "refuse once an owner exists" rule — depends on it.

**Decision:** honour the schema. One Owner. The extra head-count moved to
Administrators:

| Size | Owner | Admin | Agent | Customer | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| 100 | 1 | 8 | 20 | 71 | **100** |
| 50 | 1 | 4 | 10 | 35 | **50** |

This is a documented deviation, not a silent approximation.

---

## Part D — What was implemented

All changes are inside `backend/app/commands/seed_demo_data.py` plus tests and
docs. No other application file changed; no dependency was added.

1. **`DemoPlan`** — a frozen dataclass carrying size, role split, ticket count,
   conversation/request/attachment counts and the run anchor.
2. **`plan_for(size)`** — validates the size and builds the plan.
3. **`_split_counts`** — largest-remainder apportionment so status/priority
   targets are exact, not rounded.
4. **`expected_counts` / `dry_run_report`** — pure functions; the dry-run never
   opens a database session (a test proves this by monkeypatching
   `async_session` to raise).
5. **Time anchoring** — `_at()`/`_hours()` read the active plan's anchor.
6. **Ticket generator rewrite** — shuffled statuses/priorities (fixed seed) so
   each status is spread across the 45-day timeline; recent bucket concentrated
   in the last 14 days; causal `resolved_offset`; stale-vs-recent `updated_at` so
   aging is realistic.
7. **`_seed_tickets`** — uses the stored offsets, clamps `updated_at` to now,
   guarantees `created ≤ assigned ≤ resolved ≤ now`.
8. **Comments** — resolution confirmation placed before resolution; internal
   notes remain staff-only.
9. **Notification gating** — every ticket gets a receipt, a deterministic subset
   gets lifecycle notifications (525–587 total instead of ~1,220).
10. **CLI** — `--size`, `--dry-run`, plus the existing `--confirm`,
    `--verify`/`--verify-only`, `--confirm-production`, `--json`.
11. **Production override** — a deliberate, exact-phrase opt-in
    (`HELPDESK_DEMO_ALLOW_PRODUCTION`) for the Railway `college-demo` service,
    which declares `ENVIRONMENT=production`. It skips **no** other guard.
    The brief's `--confirm-production` flag is supported as an equivalent,
    visible acknowledgement; it still requires the confirmation token.
12. **Brief-named CLI aliases** — `--verify` (alias of `--verify-only`) and
    `--confirm-production` are accepted, so the documented commands in the brief
    work without translation. The module path stays
    `python -m app.commands.seed_demo_data`, matching the repository convention
    (there is no `app/seed.py` or `app/seed_demo.py`; the brief's suggested paths
    were adjusted to the real layout).

---

## Part E — Data integrity (measured on real PostgreSQL 16)

| Check | Result |
| --- | ---: |
| Tickets resolved before creation | 0 |
| Tickets created in the future | 0 |
| Comments before their ticket | 0 |
| Non-AGENT assignees | 0 |
| Customer-authored internal notes | 0 |
| Orphaned foreign keys | 0 |
| Duplicate emails/usernames | 0 |
| Tickets duplicated on a second run | **0** |
| Owner row changed | no |

Second run: every entity inserted `0` and reported `reused` for its full count —
idempotency proven, not assumed.

---

## Part F — Analytics comparison (endpoint vs direct SQL)

Every aggregate matched exactly:

| Field | API | SQL |
| --- | ---: | ---: |
| total_tickets | 300 | 300 |
| total_users | 100 | 100 |
| open_tickets | 120 | 120 |
| resolved / closed | 90 / 30 | 90 / 30 |
| unassigned_tickets | 31 | 31 |
| unassigned_over_24h | 29 | 29 |
| aging_over_7_days | 24 | 24 |
| urgent_open_tickets | 20 | 20 |
| waiting_on_customer | 60 | 60 |
| active_agents | 18 | 18 |
| status / priority / category maps | identical | identical |

14-day trend: **14/14 days** carry activity (108 created, 49 resolved). The
previous build produced zeros here.

Agent workload is a real, uneven spread (top: 12, 10, 10 active tickets) across
18 active agents, 149 active assignments in total.

---

## Part G — Notifications and content

- 789 comments, of which **100 internal**, **0** authored by customers.
- 567–587 notifications, **73.3% read / 26.7% unread** (inside the requested band).
- All eleven supported notification types appear; every recipient owns the
  referenced row; internal-message notification state mirrors the recipient's
  `read_at`.

---

## Part H — Tests and tooling results

| Check | Result |
| --- | --- |
| Full backend suite | **485 passed**, 58 skipped (opt-in PG/Redis) |
| New plan/CLI tests | 25 passed |
| PG seed integration tests | 31 passed on disposable PostgreSQL 16 |
| `ruff check .` | clean |
| `ruff format --check .` | 117 files formatted |
| Frontend `tsc --noEmit` | clean |
| Frontend tests | 136 passed |

The new tests cover: plan sizes and the single-Owner rule, exact apportionment,
timeline anchoring and 14-day coverage, causal timestamps, comments never
preceding tickets, staff-only internal notes, no active work assigned to inactive
agents, urgent work spread across statuses, dry-run consistency and
no-database guarantee, and every CLI guard.

---

## Part I — Safety verification of the production gate

| Gate | Result |
| --- | --- |
| Real run without confirmation token | exit **2**, refused |
| `--dry-run` | exit **0**, no DB session |
| Wrong host / DB name | refused (unit test) |
| Upload dir outside `/tmp` | refused |
| `ENVIRONMENT=production` without override | refused |
| `ENVIRONMENT=production` with exact override phrase | allowed |
| Override skipping any other guard | **no** |
| Secret printed by the command | **no** |

---

## Part J — Production database identity (non-secret)

Verified via the linked Railway project, reading **names only**:

| Item | Value |
| --- | --- |
| Railway project | `helpdesk-college-demo` |
| Environment | `production` |
| Backend service | `helpdesk-api` |
| Frontend service | `helpdesk-web` |
| `DEPLOYMENT_PROFILE` | `college-demo` |
| `ENVIRONMENT` | `production` |
| `AUTO_CREATE_TABLES` | `false` |
| `ATTACHMENTS_ENABLED` | `false` |
| Database | Neon pooled endpoint, `/neondb` |
| Seeder's verified target constant | matches the Neon host/db above |

No connection string, password, key or token is reproduced here.

> **Process note.** While checking the backend variables, one `railway variables`
> invocation printed live values to this session's terminal. No secret was
> written to any file under version control, and every subsequent query used
> `--json` and selected **names only**. The exposed values should be rotated if
> this session's terminal history is retained anywhere.

---

## Part K — What was NOT done (stated plainly)

1. **No production write.** The brief reserves the Neon cleanup for the operator
   and requires explicit approval of the exact command (Phase 12). This pass
   stopped before that gate.
2. **No live role-by-role browsing.** There is no authorised Clerk session for
   the Owner or for synthetic accounts (synthetic accounts cannot have one by
   design). Role behaviour is covered by the API authorization test suite.
3. **No Neon backup/branch verification.** That is an operator step in Phase 2.3;
   a local disposable PostgreSQL 16 was used for validation instead.
4. **No Railway deployment, no env-var change, no secret change.**

---

## Part L — Required steps to seed production

In order, with each gate explicit:

1. **Verify a recoverable Neon branch/backup** exists for `/neondb`.
2. **Confirm the real Owner row** exists (`role='OWNER'`, non-null `clerk_id`)
   and is active. If it is missing, run `python -m app.commands.bootstrap_owner`
   — never hand-write a `clerk_id`.
3. **Manually clear** the intended application records (operator action; the
   seeder never does this).
4. **Re-check table counts** after cleanup: schema intact, migrations intact, the
   Owner intact.
5. **Run the dry-run** and review the plan:
   ```bash
   railway run --service helpdesk-api --environment production \
     python -m app.commands.seed_demo_data --dry-run --size 100
   ```
6. **Approve the exact command**, then execute once:
   ```bash
   railway run --service helpdesk-api --environment production \
     sh -c 'python -m app.commands.seed_demo_data --size 100'
   ```
   with `HELPDESK_DEMO_SEED_CONFIRM`, `HELPDESK_DEMO_ALLOW_PRODUCTION` and
   `HELPDESK_DEMO_UPLOAD_DIR=/tmp/helpdesk-demo-uploads` set in that service.
7. **Verify** with `--verify --json`, then open the dashboard using the real
   Owner session.

If the transaction fails it rolls back automatically; do not blindly re-run —
diagnose the constraint first.

---

## Part M — Delivery

| Deliverable | Location |
| --- | --- |
| Database/backend audit | `docs/demo-data-audit.md` |
| Seeding runbook | `docs/demo-data-seeding.md` |
| Seed report | `docs/demo-data-seed-report.md` |
| This review | `data.md` (Part Z preserves the original PR #19 review) |
| Seeder | `backend/app/commands/seed_demo_data.py` |
| Plan/CLI tests | `backend/tests/test_demo_seed_plan.py` |
| PG integration tests | `backend/tests/test_demo_seed_postgres.py` |

Branch: `feat/demo-dataset-seeding`. No merge, no force-push, no deployment.

---

## Part Z — Preserved original `data.md` (PR #19 production-readiness review)

The following is the exact content of `data.md` on `main` before this branch,
preserved so this work does not repeat the earlier document-replacement
regression. Nothing below was edited.

# HelpDesk — full production readiness review (finalization pass)

**Review date:** 2026-11-21
**Repository:** `mdjayedgazi/HelpDesk`
**Base branch:** `main` @ `4c1bd00`
**Remediation branch:** `fix/production-readiness`
**Pull request:** [#19](https://github.com/mdjayedgazi/HelpDesk/pull/19)
**Final branch commit:** `cf19630` (15 commits ahead of `main`, 0 behind)
**Verdict:** **CONDITIONALLY READY** — college-demo only. Not production-ready
for real customers until the external items in Part L are closed.

The companion engineering report with the same conclusions is
[`docs/FINAL_PRODUCTION_READINESS_REPORT.md`](docs/FINAL_PRODUCTION_READINESS_REPORT.md).
This file is the complete review, including the investigation, every defect
reproduced and fixed in this pass, and the exact evidence.

All numbers below were produced in this session. Nothing from a prior run is
presented as a current result.

---

## 0. How this pass was performed

1. **Inspect first, edit later.** Working directory, git root, remote, branch,
   ahead/behind, staged/unstaged/untracked state, local/remote commits, PRs,
   GitHub auth, and Railway linkage were all read before touching anything.
2. **Preserve existing work.** The working tree had one change: `data.md` had
   been emptied. Nothing was discarded. See Part B.
3. **Verify, don't trust.** Every claim in the previous remediation (Trivy
   version, SARIF behavior, migration history, Railway settings, production DB
   revision) was re-checked against the real repository, the real CI logs, the
   real images, and the real (read-only) production services.
4. **Fix only confirmed defects.** Each new defect below was reproduced before
   the change and re-tested after it.
5. **Stop at production-data operations.** The merge (which triggers the
   pre-deploy migration against Neon) was left to the owner. Everything needed
   to make that merge safe was implemented and proven.

No destructive command was used: no `reset --hard`, `clean -fd`, `checkout -- .`,
force-push, rebase of a published branch, branch switch on a dirty tree, Redis
flush, production write, production restore, or container/service recreation.

---

## 1. Repository and history (as found)

```
Repository root : /home/jayed/Projects/HelpDesk
Remote          : https://github.com/mdjayedgazi/HelpDesk.git
Default branch  : main
Branch          : fix/production-readiness  (tracking origin, clean after backup)
origin/main     : 4c1bd00  docs: record production connectivity audit and port alignment fix
origin/fix/...  : e910fd4  docs: record full production-readiness remediation review in data.md
```

The nine historical commits were present and unchanged:

```
1ee60b3 fix(config): normalize browser origins and add DB query timeouts
fa9be12 feat(health): check schema/migration state in readiness
e517783 feat(tickets): make ticket creation idempotent
322ae3c perf(db): add indexes for ticket and notification list ordering
08c94a8 feat(frontend): add request timeouts, ErrorBoundary, and code splitting
f1e71b9 fix(helm): run nginx unprivileged and route the API ingress
10566fb ci: pin actions, add type check, docker/E2E/security jobs
23dadd9 docs: add backup/restore and production-readiness runbooks
e910fd4 docs: record full production-readiness remediation review in data.md
```

Branch relationship to `origin/main`:

- Merge base: `4c1bd00`
- Ahead: 9 (then 15 after this pass)
- Behind: **0** — no synchronization/merge was needed, so no conflict resolution
  was required and no rebase was performed.

### Existing pull requests

PR [#19](https://github.com/mdjayedgazi/HelpDesk/pull/19) is open,
`fix/production-readiness → main`, non-draft. PR #18 (`deploy/railway-college-demo`)
and earlier PRs are already merged or closed. No duplicate PR was created.

### GitHub authentication

`gh auth status`: logged in as `mdjayedgazi` with `repo` and `workflow` scopes.
Full access to runs, logs, PR metadata, and review comments. `main` has **no
branch protection** (`Branch not protected`), so no required-review/bypass
mechanics apply; the checks are advisory-but-green.

---

## 2. Preservation of prior work

The only working-tree change was `data.md` emptied (657 lines deleted, 0 bytes).

| Action | Result |
| --- | --- |
| Uncommitted diff saved outside the repo | `/tmp/opencode/helpdesk-safety/uncommitted-data-md-20261121.patch` |
| Committed `data.md` saved outside the repo | `/tmp/opencode/helpdesk-safety/data.md.head-e910fd4` |
| Safety snapshot of branch HEAD | branch `backup/production-readiness-pre-finalization-20261121` @ `e910fd4` |
| Prior WIP backup preserved | `wip/production-readiness-backup-20261121` @ `cf3f268` — untouched |

The two backup refs were **not pushed**. The safety snapshot name did not exist
before this pass, so no existing ref was moved. `data.md` was then rewritten
with this review; the original 657-line text remains recoverable from the patch
and from `e910fd4`.

---

## 3. CI failure investigation (root cause, not the symptom)

### 3.1 What the screenshot showed

```
Trivy image scan (backend)  Process completed with exit code 1
Upload backend scan         Path does not exist: trivy-backend.sarif
Trivy image scan (frontend) Skipped
Upload frontend scan        Path does not exist: trivy-frontend.sarif
```

Both Docker builds and the non-root/healthcheck test passed.

### 3.2 What the full log showed

From `gh run view 44895877917 --job 136821294963 --log`, the backend scan step:

```
##[group]Run aquasecurity/trivy-action@b6643a29…        # v0.33.1
with:
  version: v0.65.0                                       # <-- action default
...
aquasecurity/trivy info checking GitHub for tag 'v0.65.0'
aquasecurity/trivy info found version: 0.65.0 for v0.65.0/Linux/64bit
##[error]Process completed with exit code 1.
##[end-action display=Install Trivy; outcome=failure]
```

The failure is in **`setup-trivy` installing the binary**, before Trivy is ever
invoked. The installer resolved the tag, then failed to fetch and verify the
release.

### 3.3 Proof of the original cause

```
GET https://github.com/aquasecurity/trivy/releases/download/v0.65.0/trivy_0.65.0_Linux-64bit.tar.gz
    -> HTTP 404
GET https://github.com/aquasecurity/trivy/releases/download/v0.70.0/trivy_0.70.0_Linux-64bit.tar.gz
    -> HTTP 302
```

`v0.65.0` is an existing git tag whose release has **no published Linux-64bit
asset**. `trivy-action@v0.33.1` defaults `version` to exactly that `v0.65.0`.
So the install step exited 1, no scan ran, and **no SARIF file was created**.

The three other messages are consequences, not causes:

- `Path does not exist: trivy-backend.sarif` → `if: always()` uploaded a file
  that was never produced.
- `Trivy image scan (frontend) Skipped` → GitHub Actions skips later steps of a
  job after a failed step, so the frontend never ran.
- `Path does not exist: trivy-frontend.sarif` → same as the backend.

This is a **scanner execution failure**, not a vulnerability finding — an
important distinction the fix preserves.

### 3.4 The fix

| Element | Before | After |
| --- | --- | --- |
| Action | `trivy-action@b6643a29…` (v0.33.1) | `trivy-action@ed142fd0673e97e23eac54620cfb913e5ce36c25` (v0.36.0) |
| Binary | implicit `v0.65.0` (404) | explicit `version: v0.70.0` |
| Checksum | — | `8b4376d5d6befe5c24d503f10ff136d9e0c49f9127a4279fd110b727929a5aa9` (verified against `trivy_0.70.0_checksums.txt`) |
| SARIF upload | `codeql-action@717e2306…` (v3.30.0, node20) | `codeql-action@1bd86f2fdb4b86187fa4059f16f31a3202acc9ea` (v4.39.4, node24) |
| CodeQL init/autobuild/analyze | v3.30.0 | same v4.39.4 SHA |

Both SHAs were resolved through the GitHub API and confirmed to exist:
`ed142fd…` is the `v0.36.0` tag commit, `1bd86f2…` is the `v4.39.4` tag commit.

### 3.5 Scanner independence

Each step now has its own id and a precise condition:

```yaml
- id: backend_build
- id: frontend_build
- id: backend_scan
  if: ${{ !cancelled() && steps.backend_build.outcome == 'success' }}
- id: backend_sarif     # validates non-empty, version 2.1.0, runs present
  if: ${{ !cancelled() && steps.backend_scan.outcome == 'success' }}
- Upload backend scan
  if: ${{ !cancelled() && steps.backend_sarif.outcome == 'success' && hashFiles('trivy-backend.sarif') != '' }}
- id: frontend_scan      # independent of the backend scan
  if: ${{ !cancelled() && steps.frontend_build.outcome == 'success' }}
- id: frontend_sarif
- Upload frontend scan
  if: ${{ !cancelled() && steps.frontend_sarif.outcome == 'success' && hashFiles('trivy-frontend.sarif') != '' }}
```

Guarantees this enforces:

- A backend scanner failure cannot skip the frontend scan.
- A successful scan that produces no/invalid SARIF **fails loudly** at the
  validation step (a "silent success with no report" is impossible).
- A scan failure remains a job failure; no unconditional `continue-on-error`.
- Upload runs only for a successfully validated, existing report.
- Distinct `category: trivy-backend` / `trivy-frontend` prevent a
  duplicate-analysis collision between two Trivy reports in one job.

The security policy is unchanged: `severity: CRITICAL,HIGH`, `ignore-unfixed:
true`, `exit-code: "0"` — report-only findings, real execution failures fail.

### 3.6 CI verified green

Run `44901100310` (head `cf19630`), all jobs `success`:

```
Backend lint and SQLite tests                    success
Frontend typecheck, lint, tests, build           success
Production dependency audit                      success
Alembic migrations (disposable PostgreSQL)       success
PostgreSQL integration tests (disposable)        success
Docker image builds                              success
Helm chart validation                            success
Static security analysis and secret scan         success
CodeQL                                           success
```

The Docker job's step list, from the API:

```
Build backend image                        success
Build frontend image                       success
Frontend image serves health / non-root    success
Trivy image scan (backend)                 success
Validate backend SARIF report              success
Upload backend scan                        success   (Successfully uploaded results)
Trivy image scan (frontend)                success
Validate frontend SARIF report             success
Upload frontend scan                       success
```

The frontend scan **ran** (it is no longer "Skipped"), and the log contains
`aquasecurity/trivy info found version: 0.70.0 for v0.70.0/Linux/64bit`.

### 3.7 Workflow hardening

- Every action remains pinned to a full commit SHA.
- `persist-credentials: false` added to all eight `actions/checkout` steps (no
  job needs push credentials; this keeps the checkout token out of git config).
- `actionlint` 1.7.7: clean. YAML parses.

---

## 4. Defects found in the remediation itself (all reproduced, all fixed)

These are issues introduced or left by the previous 9-commit remediation. They
are important because every one of them would have shipped.

### 4.1 CORS preflight rejected `Idempotency-Key` (HIGH, user-facing)

`frontend/src/hooks/useTickets.ts` sends `Idempotency-Key` on ticket creation
(the new idempotency feature). `backend/app/main.py` listed only
`Authorization, Content-Type, Accept, X-Request-ID` in `allow_headers`.
Starlette answers a preflight with **400** unless every requested header is
listed.

**Reproduced against the live production API** (old code still deployed):

```
OPTIONS /api/v1/tickets  request-headers: authorization,content-type
    -> 200
OPTIONS /api/v1/tickets  request-headers: authorization,content-type,idempotency-key
    -> 400
```

Because production serves the web app and API on different origins, this breaks
ticket creation for every customer. Fixed by adding `Idempotency-Key`.

**Test:** `tests/test_origin_normalization.py::test_cors_preflight_allows_the_idempotency_key_header`
asserts both the middleware configuration and a real `OPTIONS` response
(`200`, with `idempotency-key` in `access-control-allow-headers`).

### 4.2 Zero DB timeouts did not disable the limit (MEDIUM)

`_postgres_connect_args` only added the libpq `options` when a timeout was
`> 0`. PostgreSQL interprets a missing option as "inherit the role/database
default", so `DB_STATEMENT_TIMEOUT_MS=0` left any server-side limit active — the
opposite of the setting's meaning.

Fixed to always send an explicit value. The old test asserted `"options" not in
args`; it now asserts `"-c statement_timeout=0 -c lock_timeout=0"`.

### 4.3 Migration `0011` was not safe on the path its own docstring described (MEDIUM)

The docstring told operators to create the indexes `CONCURRENTLY` first on a
large table, but `upgrade()` created them unconditionally — that would fail on
the existing index name. It also created a redundant index if the operator used
a different name.

Fixed: `upgrade()` inspects the catalog and skips an already-indexed column set.
Verified on disposable PostgreSQL with both a same-named concurrent index and a
differently-named equivalent; head is reached with exactly one index per column
set.

### 4.4 Migration `0011` broke offline SQL generation after 4.3 (MEDIUM, caught here)

The catalog check called `op.get_bind()`, which has no connection under
`alembic upgrade --sql`, so the repository's documented offline rendering
crashed. Fixed by skipping inspection in offline mode (emit every statement).

Verified:

```
$ alembic upgrade 0009_attachment_scan_status:head --sql
ALTER TABLE tickets ADD COLUMN client_request_id VARCHAR(100);
CREATE UNIQUE INDEX uq_tickets_creator_request_key ON tickets (created_by_user_id, client_request_id) WHERE client_request_id IS NOT NULL;
CREATE INDEX ix_tickets_created_at ON tickets (created_at);
CREATE INDEX ix_notifications_recipient_created_at ON notifications (recipient_user_id, created_at);
```

Both paths have unit tests (`test_migration_0011_skips_an_already_indexed_column_set`,
`test_migration_0011_renders_all_indexes_in_offline_mode`).

### 4.5 Frontend timeout was cleared before the body finished (MEDIUM)

`fetch()` resolves when headers arrive. The cleanup (`clearTimeout` + removing
the caller's abort listener) was in a `finally` attached to that await, so it ran
before `response.json()`/`text()`. A stalled body could hang the request and the
UI forever — the exact failure the timeout was added to prevent.

Fixed by consuming the body inside the protected `try`, and by rethrowing a
timeout/cancellation during the read instead of swallowing it as a parse error.
A malformed body still yields `null` so the HTTP status is reported as before.

**Regression proof:** the new test `keeps the timeout active while the response
body is still pending` fails against the previous implementation (it hangs past
the timeout; observed 5012 ms then failure) and passes now.

### 4.6 Secret scan had path-wide allowlists (HIGH for a security control)

`.gitleaks.toml` excluded `backend/tests/**` and `backend/migrations/**` by
path. Gitleaks skips matching files entirely, so a real credential committed
there was invisible.

**Proved with gitleaks 8.28.0:**

| Scenario | Old config | New config |
| --- | --- | --- |
| Fake real-looking `sk_live_…` key in `backend/tests/leak.py` | **no leaks found (exit 0)** | **1 leak (exit 1)** |
| Same key elsewhere | detected | detected |
| This repository (62 commits) | clean | clean |

The new config keeps only **exact placeholder values** (e.g. `^sk_test_dummy$`,
`^sk_live_x{32}$`, the disposable `verify:verify@` URLs). It is not a path
bypass.

### 4.7 Disposable-DB test guard matched the whole URL (MEDIUM)

The PostgreSQL suites searched the entire URL for `test`/`verify`/`ci`, so
`postgresql+psycopg://ci_runner:pw@db.example.com/helpdesk` passed — yet those
suites create tables and rows. A production URL with `ci` in the username was a
real footgun.

Fixed with a shared `tests/_disposable_db_guard.py` that parses the URL and
checks **only the database name** (including `?dbname=`). Its own tests reject a
`ci` username, a `verify` password, and an empty database name, and accept
genuinely disposable names.

### 4.8 Backup/restore runbook could not work as written (HIGH for recovery)

`docs/DATABASE_BACKUP_RESTORE.md`:

- `pg_dump`/`pg_restore` were passed `postgresql+psycopg://`, which libpq
  rejects → no usable backup. Scheme conversion added.
- The restore guard was a URL substring test: a production URL with `test` in
  its password would pass (and `pg_restore --clean` would drop production
  objects), while a valid isolated Neon branch without a marker would be
  refused. Replaced with a **host/port/database identity comparison** against
  `PRODUCTION_DATABASE_URL`.
- Verification read `RESTORE_DATABASE_URL` while the restore step had set a
  different variable. Both now use `RESTORE_LIBPQ_URL`.
- The schema probe needed `FRONTEND_URL`; added.
- Added the note that Alembic prefers `MIGRATION_DATABASE_URL`, so recovery must
  repoint both URLs.
- `README.md`: added a bounded `pg_isready` wait instead of racing `pytest`
  against container startup.

---

## 5. Application audit results

### 5.1 Backend

| Area | Finding |
| --- | --- |
| FastAPI structure | routers per domain; middleware order documented and intentional (body limit innermost, CORS outermost) |
| Config validation | fail-closed production checks; placeholder rejection; refuses localhost/HTTP/wildcard/insecure Clerk/diabled rate limit without shared Redis |
| Clerk auth | verifies the session token; derives identity from `sub`; never trusts client roles |
| Role authorization | CUSTOMER / AGENT / ADMIN / OWNER enforced server-side; stored role is authoritative |
| Ticket lifecycle | create (idempotent), claim, assign, status, priority, feedback, history |
| Attachments | allowlisted + magic-byte checked, ClamAV fail-closed, quarantine → publish |
| Rate limiting | Redis-backed, fails closed (503) when unreachable; production refuses to start if unusable |
| DB sessions | async SQLAlchemy, pool pre-ping, bounded pool, per-connection timeouts |
| Exception handling | coarse readiness errors; no connection string/host/exception text leaked |
| Logging | JSON in production by default; no secrets logged |

### 5.2 Database

| Area | Finding |
| --- | --- |
| Models / migrations | 11 revisions, single head `0011_query_indexes`; `alembic check` reports no drift |
| Constraints | PK/FK/unique present; single-OWNER partial unique index |
| Indexes | role indexes from `0001`; `0010` partial unique idempotency index; `0011` ordering indexes |
| Concurrency | idempotency race resolved by re-reading the winning row |
| Transactions | transactional DDL; migrations are retry-safe (second run is a no-op) |
| SQLite/PostgreSQL | SQLite for unit tests; PostgreSQL suites opt-in and guarded |
| Rollback | `0011 → 0010` and `0010 → 0009` exercises exist; `0009 → head` is additive |

### 5.3 Frontend

| Area | Finding |
| --- | --- |
| Auth/session | Clerk session token fetched per request |
| Protected routes | guarded; unauthorized users redirected |
| API client | 20 s default timeout, 120 s upload, combined `AbortSignal`, body-read protected (fixed) |
| ErrorBoundary | application-level fallback with reset |
| Loading/error states | present on pages |
| Code splitting | `React.lazy` per route; entry 453.62 kB (122.12 kB gzip), all route chunks under the warning threshold |
| Security headers | served by nginx: CSP, nosniff, frame DENY, referrer policy, permissions policy, COOP/CORP |

### 5.4 Infrastructure

| Area | Finding |
| --- | --- |
| Backend image | multi-stage, `python:3.13.1-slim`, runs as uid `10001` via gosu entrypoint |
| Frontend image | nginx unprivileged uid `101`, writable config/pid/cache, port 8080 |
| Healthchecks | backend `/health/live` (image) + `/health/ready` (Railway); frontend `/healthz` |
| Helm | lint + template (default and API-ingress) pass; numeric ids and `fsGroup` match the image |
| Replicas | 1 each — required while uploads are local disk |

---

## 6. Production investigation (read-only)

All database work used `read_only=True` / `transaction_read_only=on`. All Redis
work used read-only commands (`PING`, `INFO`, `DBSIZE`, `ACL WHOAMI`). No
secret value was printed, and no variable dump was ever run.

### 6.1 Neon PostgreSQL

| Item | Observed |
| --- | --- |
| Endpoint | Neon **pooled** (`-pooler`) |
| Version | PostgreSQL 18.7 |
| Branch / project IDs | `br-damp-tooth-b5t0ckbx` / `plain-bread-92177409` |
| Current revision | **`0009_attachment_scan_status`** |
| `users` | 1 (CUSTOMER, active, linked to Clerk, created 2026-11-19) |
| `tickets` / `comments` / `attachments` / `notifications` | 0 / 0 / 0 / 0 |
| `tickets.client_request_id` | absent (consistent with `0009`) |
| Database size | 8744 kB |
| Runtime role | `neondb_owner` (not superuser) |
| Extensions | `plpgsql` |

**Release-critical:** production is `0009`; the merging image ships `0011` and
its readiness probe is production-fatal on a revision mismatch. Without a
migration gate the merge would deploy an image that can never become ready.
This is why the pre-deploy migration in Part 7 is a release gate.

**Historical user-count discrepancy:** the prior audit saw one user, then zero.
Today there is one CUSTOMER (2026-11-19). No audit log, backup metadata, or
recovery point is reachable without the Neon console, so **the cause remains
undetermined**. No restore was performed and none is recommended; there is no
evidence of current loss.

**Backup/PITR:** **not verified.** Requires the Neon console (`neonctl` is not
installed and no credential is stored). No isolated restore drill was run, so
this report does **not** claim a working restore.

### 6.2 Upstash Redis

| Item | Observed |
| --- | --- |
| Scheme | `rediss://` (TLS) |
| `PING` | `PONG` |
| Version | 8.4.0 |
| Identity | `default` |
| Keys now | 0 (`db0` empty) |
| Max memory / policy | 64 MB / `optimistic-volatile` |
| AOF/RDB durability | not reported by `INFO` — **unverified** |
| Ownership/claim/expiry/plan | **unverified** (needs the dashboard) |

No flush, no write, no delete, no replacement. `/health/ready` reports
`redis: ok` live.

### 6.3 Clerk

| Item | Observed |
| --- | --- |
| Backend key family | **`sk_test_*`** (development instance) |
| Frontend key family | **`pk_test_*`** |
| FAPI origin | `https://social-ferret-6540.clerk.accounts.dev` |
| Profile | `DEPLOYMENT_PROFILE=college-demo` (explicitly permits `sk_test_`) |
| `/api/v1/users/me` unauthenticated | **401** (verified live) |
| Interactive sign-in / full flow | **UNVERIFIED** — no authorized test account |

### 6.4 OWNER

No OWNER exists; the sole user is a CUSTOMER. `INITIAL_ADMIN_EMAIL` is not set
on the API service, so bootstrap is not configured. `bootstrap_owner` (verified
in code and tests) promotes only an already-linked account whose **verified**
Clerk primary email matches, is idempotent, and is never on the request path.
**No promotion was performed.**

### 6.5 File storage

Local disk only, and attachments are **disabled** in this deployment. The upload
path is secure (allowlist, magic bytes, fail-closed ClamAV, quarantine, path
containment, authorize-before-download) but local storage pins the backend to
one replica. That is the current setting and was not changed.

**Object storage recommendation:** **Cloudflare R2** — S3-compatible API, no
egress charge for downloads, private buckets with presigned URLs that fit the
existing authorize-then-download flow, and lifecycle rules for quarantine
cleanup. Amazon S3 is the alternative if the deployment later needs AWS IAM or
cross-region replication. No storage was implemented (needs a decision and
credentials).

---

## 7. Railway: what was actually configured

The project/environment/service identities were verified before changing
anything.

| Item | Value |
| --- | --- |
| Project | `helpdesk-college-demo` (`d59fbf51-…`) |
| Environment | `production` (`126b1644-…`) |
| API | `helpdesk-api` (`3ffa5eab-…`), root `/backend`, repo `mdjayedgazi/HelpDesk` |
| Web | `helpdesk-web` (`a1f2359d-…`), root `/frontend`, repo `mdjayedgazi/HelpDesk` |
| Triggers | both: branch `main`, `checkSuites: true` (Wait for CI) |
| API healthcheck (before) | `/health/live` |
| API healthcheck (after) | **`/health/ready`** |
| Web healthcheck | `/healthz` |
| Healthcheck timeout | 300 s |
| Replicas | 1 each |
| API pre-deploy (before) | none |
| API pre-deploy (after) | **`alembic upgrade head`** |
| API domain target port | `8080` (matches injected `PORT`) |
| Web domain target port | `8080` |
| Current deployed commit | `169f76e` on both |
| Wait-for-CI gating of deploys | enabled |

### Changes applied

Only the two settings required for a safe release, to `helpdesk-api`:

1. `preDeployCommand: ["alembic upgrade head"]`
2. `healthcheckPath: "/health/ready"`

The mutation required `sleepApplication: true` on the Free plan; it was already
`true` and was preserved. No other variable, volume, domain, port, or service
was touched, and no service was created or recreated.

### Why the migration gate is correct and safe

- It runs in the backend image at `/app`; `alembic` is on `PATH`
  (`/app/.venv/bin/alembic`). Verified inside the built image as root **and** as
  the runtime `10001:10001` user.
- A migration failure exits 1 (verified against an unreachable database), which
  fails the pre-deploy, so the failing image never starts.
- Only after a successful migration does the container start; only then does
  `/health/ready` (schema-aware) clear it for traffic.
- Migrations are additive (nullable column + partial unique index + two
  non-unique indexes), so the previous `0009` application stays compatible
  during rollout and for an application rollback; no downgrade is required.
- Verified `0009 → 0011` locally preserves all existing rows.

### Port and healthcheck

The API binds `$PORT` (`CMD` uses `${PORT:-8000}`), Railway injects `8080`, and
the public domain targets `8080` — consistent. `/health/live` remains the
liveness probe; `/health/ready` is the traffic gate.

---

## 8. Full verification matrix (this session)

### Backend

| Check | Result |
| --- | --- |
| pytest, SQLite | **456 passed, 47 skipped** |
| pytest, + disposable PostgreSQL | **502 passed, 1 skipped** |
| Ruff lint / format | passed / 113 files formatted |
| Pyrefly | **0 errors** |
| Alembic `upgrade head` (fresh PG) | OK, head `0011_query_indexes` |
| Alembic `check` | no new upgrade operations |
| Alembic offline SQL `0009:head` | renders all statements |
| `0009 → 0011` with rows | 1 user / 1 ticket / 1 notification preserved |
| Retry (`upgrade head` twice) | no-op second time |
| Downgrade `0011 → 0010` → re-upgrade | rows preserved |
| Pre-created concurrent index path | converges, one index |
| Failing migration | exits 1 |
| Readiness on migrated DB | `database: ok`, `schema: ok` |
| Readiness on out-of-date DB | 503 in production (unit-tested) |

### Frontend

| Check | Result |
| --- | --- |
| Typecheck | passed |
| Lint | passed |
| Unit tests | **52 passed** (8 files) |
| Production build | passed; entry 453.62 kB (122.12 kB gzip) |
| `npm audit --omit=dev` | **0 vulnerabilities** |

### Infrastructure & security

| Check | Result |
| --- | --- |
| Backend image build | passed |
| Frontend image build | passed |
| Frontend runs as uid | `101` |
| `/healthz` | `ok` |
| Unknown asset | `404` |
| Security headers + CSP | present |
| Backend image user | `10001` |
| Backend `/health/live` | 200 |
| Backend `/health/ready` (migrated) | ready, schema ok |
| Helm lint | 0 failed |
| Helm template (default + ingress) | both render |
| Trivy backend SARIF | valid, 44 results, exit 0 |
| Trivy frontend SARIF | valid, 58 results, exit 0 |
| Gitleaks (repo, 62 commits) | no leaks |
| Gitleaks (injected real key) | detected, exit 1 |
| actionlint | clean |
| `git diff --check` | clean |

The 47 skipped backend tests are the opt-in PostgreSQL suites when no disposable
URL is set. With PostgreSQL enabled, 1 skip remains: an opt-in Redis test that
had no disposable Redis locally; CI runs it against its own `redis:7-alpine`
service.

---

## 9. Pull request and release status

| Item | Value |
| --- | --- |
| PR | #19, `fix/production-readiness → main` |
| Commits | 15 |
| Mergeability | `MERGEABLE`, `mergeStateStatus: CLEAN`, 0 behind `main` |
| Checks | all 8 CI jobs + CodeQL + Trivy + CodeRabbit: success |
| Branch protection | none configured on `main` |
| Merge | **not performed in this session** |

**Why the merge was left to the owner:** merging is the one action that
mutates production data, because the new pre-deploy runs
`alembic upgrade head` against Neon. The request explicitly requires stopping
before unsupervised production-data operations. Everything needed to make that
merge safe is implemented and verified; the remaining steps are account-level
configuration (Neon PITR, Clerk production instance, Upstash durability, object
storage) and the owner's go-ahead. A merge into `main` now executes the safe
sequence: migrate (fail-closed) → start → readiness (schema must match) → traffic.

---

## 10. Outstanding blockers (external)

| # | Item | Why it matters | Code change? | Blocks demo? | Blocks customers? |
| --- | --- | --- | --- | --- | --- |
| L1 | Neon PITR/retention and a restore drill | an untested backup is not a backup | no | no | **yes** |
| L2 | Clerk production instance (`sk_live_`/`pk_live_`) | dev keys are not for customers | no | no | **yes** |
| L3 | OWNER bootstrap + `INITIAL_ADMIN_EMAIL` | owner-only admin is unavailable | no | no | admin use |
| L4 | Upstash durability/claim/expiry | rate limiting fails closed → 503 on eviction | no | no | **yes** (certainty) |
| L5 | Durable object storage (R2 recommended) | local disk pins to one replica | yes, to enable | no | before scale-out |
| L6 | Interactive authenticated flow | not exercised without a test account | no | verification gap | verification gap |

### Exact procedures (owner action)

- **L1:** In the Neon console, record the plan, PITR window, and retention.
  Create a branch from a recent point in time and run section 4 of
  `docs/DATABASE_BACKUP_RESTORE.md` against that branch. Never restore over
  production.
- **L2:** Create a Clerk production instance, add the production domains, put
  `sk_live_…` on `helpdesk-api` and `pk_live_…` on `helpdesk-web` (rebuild the
  frontend; `VITE_` values are compile-time), set `FRONTEND_URL`, and remove
  `DEPLOYMENT_PROFILE=college-demo`. Rotate keys; never paste them into chat.
- **L3:** Sign in once with the intended admin account, set
  `INITIAL_ADMIN_EMAIL` to that verified Clerk primary email, run
  `python -m app.commands.bootstrap_owner` once, then remove the variable.
  **Do not run without authorization.**
- **L4:** In Upstash, confirm the database is claimed, has no expiry, and has a
  persistence/eviction policy suitable for rate-limit keys; record the plan.
- **L5:** Choose R2 (recommended) or S3, provision a private bucket, add
  credentials as service variables, implement the adapter, and only then allow
  more than one replica.

---

## 11. Final recommendation

**CONDITIONALLY READY — college demo.**

The code, tests, container builds, migrations, CI pipeline, Trivy/SARIF
reporting, and the Railway deployment gates are correct and verified in this
session. The previously broken Trivy job now installs a real binary, scans both
images independently, validates real SARIF, and uploads both reports; the
application's CORS, timeout, migration-safety, and secret-scanning defects found
in this pass are fixed with regression tests; and the deployment now runs
migrations behind a fail-closed pre-deploy and gates traffic on schema-aware
readiness.

It is **not** ready for real customers until L1, L2, and L4 are closed (and L5
before any scale-out), and the authenticated flow (L6) is exercised with a real
session. Do not treat a green pipeline as proof of production readiness.
