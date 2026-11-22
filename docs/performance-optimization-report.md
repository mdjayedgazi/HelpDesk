# HelpDesk — System-Wide Performance Optimization Report

- **Date:** 2026-11-22
- **Branch:** `perf/system-data-fetching-redis-postgres`
- **Base:** `main` @ `34ca285` (after PR #31)
- **PR target:** `main`
- **Verdict:** **IMPLEMENTED — CI PASSING, AWAITING MERGE** (not deployed).
- **UI:** unchanged. The only frontend files touched are two internal hooks/effects
  (`useTickets.ts`, one effect in `TicketsPage.tsx`). No JSX, layout, spacing,
  color, typography, controls, or animation changed.

---

## 1. Executive summary

The application is genuinely slow to switch ticket pages, but not because of query
execution. Measured against the live Neon database:

- **PostgreSQL executes the ticket page query in ~3.5 ms** (`EXPLAIN ANALYZE`, 300
  tickets / 224 kB total). The planner is fine.
- **A single database round-trip from the developer vantage is ~305 ms**, and the
  ticket endpoint issued **two sequential round-trips** (a `COUNT(*)` then the
  page). A `SELECT 1` costs the same ~305 ms as the real query — the cost is
  **network round-trips to Neon**, not the database.

So the dominant bottleneck is **the number of sequential database round-trips per
request**, amplified by (a) the owner-reconciliation path doing an extra
advisory-lock query **and a Clerk API call on every authenticated request**, and
(b) the dashboard analytics aggregate issuing **14 sequential queries** with no
caching.

The optimizations reduce **round-trips per request**, not query cleverness:

| Change | Before | After |
| --- | --- | --- |
| Ticket list statements (per request) | 3 (auth, count, page) | **2** (auth, count+page) |
| Owner ticket request statements | 3 DB + advisory-lock query + Clerk call | **2 DB, no advisory lock, no Clerk call** |
| Analytics endpoint DB cost | ~14 sequential round-trips every load | **0 on cache hit** (Redis), 14 on miss |

No paid plan upgrade is required or recommended.

---

## 2. System architecture (as discovered)

- **Backend:** FastAPI (async), SQLModel/SQLAlchemy 2.1 over `psycopg` v3, single
  uvicorn worker (Dockerfile `CMD`), Alembic migrations run as a Railway
  pre-deploy step.
- **Database:** Neon PostgreSQL **18.7** via the **pooled** endpoint
  (`…-pooler…`), 300 tickets / 100 users, `tickets` total size 224 kB.
- **Redis:** one Railway Redis, currently used **only** for write rate limiting
  (`app/core/rate_limit.py`); not used for caching before this work.
- **Frontend:** React 19, TanStack Query **5.104.3**, `staleTime` 15 s / `gcTime`
  5 min globally, `keepPreviousData` on ticket lists, query keys include full
  params (page included).
- **Connection pool:** `pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`,
  `pool_recycle=1800`, no upstream scaling beyond one worker. Total ≤ 15
  connections — well within Neon's `max_connections=901`.

---

## 3. PostgreSQL

- **Actual server version:** `PostgreSQL 18.7 (84da7d8) on aarch64-unknown-linux-gnu`
  (verified read-only with `SELECT version()` / `SHOW server_version`).
- **Connection:** pooled Neon endpoint; engine uses `psycopg` async with explicit
  statement/lock timeouts. No change was needed.
- **Query plans (read-only `EXPLAIN (ANALYZE, BUFFERS)`, live Neon):**
  - unfiltered page: `Seq Scan → WindowAgg → top-N Sort → Limit`, **execution
    3.55 ms**, planning 8.6 ms (first run; subsequent plans cached).
  - status-filtered page: **0.13 ms**.
  The tables are tiny; adding B-tree indexes for these predicates would not help
  and would add write overhead, so **no new indexes were added**.
- **Index review:** existing `ix_tickets_created_at`, `ix_tickets_assignee_user_id`,
  `ix_tickets_created_by_user_id`, `tickets_pkey`, and the idempotency partial
  unique index already cover the list ordering and scopes. No duplicates, nothing
  removed.
- **Conclusion:** the database is not the bottleneck; round-trip count is.

---

## 4. Frontend

- **Cache strategy:** ticket-list pages already use `keepPreviousData` (the
  previous page stays visible while the next loads — unchanged). Query keys
  already include the full params, so revisiting a page is served from cache.
  The list `staleTime` is now a short, explicit **30 s** (was the 15 s global):
  it avoids redundant refetches of a page you just visited without hiding updates
  (mutations still invalidate `['tickets']`).
- **Prefetch:** new `usePrefetchTicketPage` warms **only the immediate next page**
  after the current page renders and only when `has_next` is true and the page is
  not already cached. It uses the same key/fetch as the visible query, so it can
  never show different data. This makes a predictable Next click render from
  cache. It does not loop and does not fetch pages you are unlikely to visit.
- **Rendering:** no component re-architecture. Ticket rows, table, pagination and
  layout are untouched. `keepPreviousData` already prevented loading-state resets;
  the prefetch removes most perceived waiting on forward paging.
- **No visual change:** verified in the diff — `TicketsPage.tsx` gains one hook
  call and one `useEffect`; no JSX/markup/style edits. All style files are
  untouched.

---

## 5. Backend

- **Ticket list (the reported slow path):** replaced the two sequential queries
  (`COUNT(*)` then the page) with **one** query using
  `count(*) OVER ()` (`count_and_page_tickets`). The window is evaluated before
  `LIMIT`, so the total is computed over the exact same filtered set — identical
  results to the two-query version (verified on PostgreSQL: same total, same rows;
  deep-past-end pages fall back to a single `COUNT`). Deterministic ordering
  (`created_at DESC, id DESC`) is unchanged.
- **Owner reconciliation fast path (request path):** `_reconcile_owner_for` ran an
  advisory-lock query **and** a Clerk `users.get_async` on **every** authenticated
  request when `OWNER_EMAIL` is configured. For a caller who **already holds
  OWNER**, reconciliation can only return `already_owner`/`not_verified` (both
  `changed == False`), so it is now skipped for that caller. A *new* configured
  owner still takes the full path and is promoted exactly as before (covered by
  existing tests). This removes one DB round-trip **and** one external API call
  from every page switch the Owner makes.
- **N+1 findings:** none in the ticket list (3 → 2 statements, no per-row
  queries). The dashboard analytics deliberately runs many aggregate queries
  (now cached; see §6).
- **Serialization / contracts:** no API contract change. `TicketPage` shape, roles,
  pagination semantics and timeouts are unchanged.

---

## 6. Redis

**Existing use:** write rate limiting only (fixed-window counters, fail-closed).

**New use (optional, off by default):** a small cache-aside layer
(`app/core/cache.py`) for the **admin support analytics** aggregate, the most
expensive read endpoint (≈14 sequential queries). It reuses the same Redis
instance — `CACHE_REDIS_URL` defaults to `RATE_LIMIT_REDIS_URL`.

- **Cache keys:** `helpdesk:cache:analytics:support:v<version>` (namespaced so it
  never collides with `helpdesk:rate:*`).
- **TTL:** 60 s safety net; correctness of freshness comes from invalidation, not
  the TTL.
- **Invalidation:** a single `INCR helpdesk:cache:analytics:version` after a
  successful analytics-affecting write (ticket create/update/claim/assign; user
  profile/role/status). The version is part of the key, so one `INCR` logically
  invalidates every cached payload — **no `KEYS`, no `FLUSHDB`/`FLUSHALL`, no
  key scans.** Invalidation runs **after** the response is sent, adding no client
  latency, and only for 2xx responses. Comments/attachments/feedback/messaging do
  **not** invalidate (they do not affect the aggregate) — verified by test.
- **Failure handling:** every Redis operation is wrapped; any `RedisError`,
  timeout or malformed value is treated as a **miss** and the request reads
  PostgreSQL. Caching can never break a request or return wrong data.
- **Stampede protection:** a short `SET NX PX` rebuild lock means one concurrent
  miss rebuilds; losers compute directly (still correct) rather than block.
- **Security:** keys carry no user data; the cache is only reached by the
  admin-gated analytics endpoint; no secrets are logged (only key names / error
  class). Authorization is unchanged — the cache does not cache authorization
  decisions, only the already-authorized aggregate payload for admins/owners.
- **Enabling:** set `CACHE_ENABLED=true` (and optionally `CACHE_REDIS_URL`, which
  defaults to the rate-limit Redis URL). Default is `false`, so the change is a
  no-op unless explicitly enabled.

---

## 7. Performance measurements

All numbers are from a developer machine → Neon (a **high-latency** vantage of
~305 ms/round-trip), PostgreSQL 18.7, 300 tickets. They demonstrate the
**round-trip** effect; absolute production (Railway→Neon, same region) latencies
will be much smaller but the **relative** round-trip savings hold.

| Measurement | Before | After |
| --- | --- | --- |
| Ticket list DB round-trips | 2 (count + page) | **1** (count+page) |
| Ticket list SQL statements/request | 3 | **2** |
| Two round-trips vs one (measured, live Neon) | **679.8 ms** | **307.3 ms** |
| **Saved per ticket list request** | — | **≈372 ms** (this vantage) |
| Owner request: extra advisory-lock query | yes (1 round-trip) | **no** |
| Owner request: Clerk `users.get_async` | every request | **none when already Owner** |
| Analytics DB round-trips | ~14 every load | **0 on cache hit** |
| 14 sequential round-trips (cache-miss lower bound) | **≈6,980 ms** | n/a |

`EXPLAIN ANALYZE` execution time for the page query itself was **3.5 ms** — i.e.
<1 % of the round-trip cost — confirming the optimization target (network
round-trips) was correct.

**What could not be measured here:** deployed Railway→Neon latency (the frontend
`.env` points at localhost), and end-to-end browser timing (not reproducible in
this environment). Those are stated as production-check items in §11.

---

## 8. Tests

### Backend (all pass)
- `ruff check`, `ruff format --check`, `pyrefly` (0 errors).
- `pytest`: **580 passed, 72 skipped** (the 72 are the opt-in PostgreSQL suites,
  all run separately below).
- New `tests/test_analytics_cache.py` (7): miss→compute→populate; hit avoids DB;
  analytics-affecting write bumps the version; unrelated write does **not**
  invalidate; Redis-down fallback to DB; corrupt entry treated as a miss;
  atomic/exclusive rebuild lock; Redis errors swallowed.
- New owner fast-path test: an existing Owner request **does not call Clerk** and
  still returns `owner`.
- Existing owner-promotion, authorization, pagination, and analytics tests
  unchanged and green.

### PostgreSQL (disposable, exact CI order, fresh DB)
- E2E 2 passed; `test_postgres_integration` + `test_support_workflows_postgres` +
  `test_internal_messages_postgres` + `test_qa_seed_postgres` +
  `test_migration_0012_staff_mentions` = **32 passed**; demo-seed **31 passed**.
- Window-function pagination verified equivalent to the two-query result on real
  PostgreSQL (same total, same rows; empty past-end falls back to `COUNT`).

### Frontend
- `typecheck` pass, `lint` pass.
- `npm test`: **228 passed / 23 files** (new `useTickets.test.tsx`: prefetch uses
  the same key, skips cached pages, no-op without params; `keepPreviousData`
  retains the previous page).
- Production `build` pass.

---

## 9. Data safety

- Neon was only ever accessed **read-only** (`SET TRANSACTION READ ONLY`;
  `SELECT`/`SHOW`/`EXPLAIN` only). No DDL/DML was executed against it.
- **No migration is required** for this work (no schema change; no new index —
  existing indexes were shown sufficient).
- No seeders, truncation, drops, or owner changes. Credentials were never printed
  (one earlier inspection error was handled without echoing the DSN).
- All performance testing used disposable local PostgreSQL containers and
  in-memory fakes; none touched Neon.

---

## 10. Git

- Branch: `perf/system-data-fetching-redis-postgres` (from `main` @ `34ca285`).
- Commits: see the branch (`perf: optimize system-wide data fetching and caching`).
- PR: **https://github.com/mdjayedgazi/HelpDesk/pull/32** (targets `main`).
  **All CI checks pass** — Backend lint + SQLite tests, Frontend
  typecheck/lint/tests/build, Alembic migrations, PostgreSQL integration, Docker
  image builds, Production dependency audit, Helm validation, Static security +
  secret scan, CodeQL, Trivy.

---

## 11. Deployment

- **No migration.** Railway's pre-deploy `alembic upgrade head` is a no-op for
  this change.
- **No env change required.** Caching is off by default; to enable it in
  production set `CACHE_ENABLED=true` (it reuses the existing rate-limit Redis
  URL). This is optional and independent of correctness.
- Deploy order: backend first (new query path + optional cache), frontend can
  follow in the same merge — the API contract is unchanged, so either order is
  safe.
- Post-deploy verification (read-only / observational):
  1. Switch ticket pages: previous page stays visible, next page appears quickly.
  2. `GET /api/v1/tickets?page=2` returns the same `total`/items as before.
  3. If `CACHE_ENABLED=true`: reload the admin dashboard twice; the second load is
     fast. Create a ticket; the dashboard totals update (invalidation works).
  4. Redis down (if cache enabled): ticket pages and dashboard still load (DB
     fallback).

---

## 12. Remaining limitations

- Production Railway→Neon latency was not directly measurable from this
  environment; the optimizations target round-trip **count**, which is
  latency-independent, but exact milliseconds should be confirmed from Railway.
- The cache is intentionally analytics-only. Ticket lists were not cached because
  they are authorization-scoped, mutation-frequent, and already served from the
  TanStack cache + prefetch; a server cache there would add invalidation risk for
  little gain on this workload.
- Offset pagination is retained (correct and adequate at this scale); cursor
  pagination was not adopted because there is no evidence deep-page cost is the
  problem (execution is ~3 ms at 300 rows).
