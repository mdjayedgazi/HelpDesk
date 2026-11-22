# HelpDesk — System-Wide Performance Optimization Review

**Date:** 2026-11-22
**Branch:** `perf/system-data-fetching-redis-postgres`
**Base:** `main` @ `34ca285` (after PR #31 hotfix merge)
**Companion report:** [`docs/performance-optimization-report.md`](docs/performance-optimization-report.md)
**Verdict:** **IMPLEMENTED — CI PASSING, AWAITING MERGE** (not deployed). **UI unchanged.**

> **Document preservation.** The 0012 migration hotfix review and everything
> beneath it follow verbatim. This review is prepended.

---

## Part A — Repository and remote state

| Item | Finding |
| --- | --- |
| `main` HEAD at start | `34ca285` — merge of PR #31 (0012 migration hotfix) |
| `origin/main` | matches `main` @ `34ca285` |
| Prior branches | width/motion, pagination, mentions, migration hotfix all **merged** |
| Untracked at start | harness files only |
| `data.md` | emptied locally; restored from `HEAD` before prepending |
| New branch | `perf/system-data-fetching-redis-postgres` |

---

## Part B — The real bottleneck (measured, not assumed)

PostgreSQL **18.7** (verified read-only with `SELECT version()`), pooled Neon
endpoint, 300 tickets / 100 users, `tickets` total size **224 kB**.

- `EXPLAIN (ANALYZE, BUFFERS)` of the ticket page query: **execution 3.5 ms**
  (unfiltered), **0.13 ms** (status-filtered). The planner is fine; indexes are
  sufficient.
- A single round-trip from the developer vantage is **~305 ms**, and a bare
  `SELECT 1` costs the same as the real query → the cost is **network
  round-trips**, not execution.
- `GET /tickets` issued **two sequential round-trips** (count then page), plus,
  for the Owner, an advisory-lock query **and a Clerk API call on every request**.
- Dashboard analytics issues **~14 sequential queries** with no caching.

Measured, live Neon:

| | Before | After |
| --- | --- | --- |
| Ticket list round-trips | 2 (count+page) | **1** |
| Ticket list SQL statements | 3 | **2** |
| 2 vs 1 round-trip | **679.8 ms** | **307.3 ms** (**−372 ms**) |
| Analytics | ~14 round-trips/load | **0 on cache hit** |

---

## Part C — Frontend optimizations (no visual change)

- Ticket-list `staleTime` set to an explicit 30 s (was 15 s global): revisited
  pages come from cache; mutations still invalidate `['tickets']`.
- New `usePrefetchTicketPage`: warms **only the immediate next page**, only when
  `has_next` and not already cached, using the same query key/fetch — so it can
  never show different data. Predictable Next clicks render from cache.
- Verified: only `useTickets.ts` and one effect in `TicketsPage.tsx` changed; **no
  JSX/markup/style edits**. `keepPreviousData` (previous page stays visible while
  the next loads) was already present and is preserved.

---

## Part D — Backend optimizations

- `count_and_page_tickets`: one query with `count(*) OVER ()` replaces the
  `COUNT(*)`+page pair. The window is computed before `LIMIT`, so the total is
  identical to the old two-query result (verified on PostgreSQL; empty past-end
  pages fall back to a single `COUNT`). Ordering unchanged.
- Owner reconcile fast path: an existing **OWNER** request skips the advisory
  lock and Clerk `users.get_async` (reconciliation cannot change an owner —
  `evaluate` returns `already_owner`/`not_verified`, `changed=False`). A *new*
  configured owner still takes the full path and is promoted as before (covered
  by tests). This removes one round-trip + one external call from **every** Owner
  request.
- No N+1 in the ticket list; no API contract change.

---

## Part E — Redis (analytics cache-aside, optional)

- Reuses the existing Redis (rate limiting); `CACHE_REDIS_URL` defaults to
  `RATE_LIMIT_REDIS_URL`. Off unless `CACHE_ENABLED=true`.
- Cache key `helpdesk:cache:analytics:support:v<version>`, TTL 60 s.
- Invalidation: one `INCR` of a version key after analytics-affecting writes
  (ticket create/update/claim/assign; user profile/role/status), after the
  response is sent. No `KEYS`, no `FLUSHDB`/`FLUSHALL`, no key scans. Comments and
  other unrelated writes do **not** invalidate (test-verified).
- Any Redis error/timeout/corrupt value = cache miss → PostgreSQL. Caching can
  never break a request or return wrong data.
- Stampede: short `SET NX PX` rebuild lock; losers compute directly.
- Security: no user data in keys, admin-gated endpoint only, no secrets logged,
  authorization unchanged.

---

## Part F — Tests and results

- Backend: ruff / ruff-format / pyrefly clean; `pytest` **580 passed, 72 skipped**.
  New `tests/test_analytics_cache.py` (7: miss/hit, invalidation, non-invalidation,
  Redis-down fallback, corrupt entry, stampede lock, swallowed errors) + an owner
  fast-path test (no Clerk call). Existing owner/auth/pagination/analytics tests
  unchanged and green.
- PostgreSQL (disposable, exact CI order, fresh DB): E2E 2; PG suites + migration
  module **32**; demo-seed **31** — all pass. Window pagination proven equivalent
  to the two-query result on real PostgreSQL.
- Frontend: typecheck + lint pass; **228 tests / 23 files** (new
  `useTickets.test.tsx`); production build pass.

---

## Part G — Data safety

Neon accessed **read-only** only (`SET TRANSACTION READ ONLY`; SELECT/SHOW/EXPLAIN).
No migration needed (no schema change; existing indexes shown sufficient). No
seeders, drops, truncation, or owner changes. No credentials printed. All perf
testing on disposable local PostgreSQL or in-memory fakes.

---

## Part H — Delivery

- Branch: `perf/system-data-fetching-redis-postgres`
- No migration; no env change required (cache is opt-in via `CACHE_ENABLED`).
- PR against `main` (URL recorded after creation; see PR). Not merged/deployed.

### Post-deploy verification

1. Switch ticket pages: previous page stays visible; next page loads fast.
2. `GET /api/v1/tickets?page=2` returns the same `total`/items.
3. If `CACHE_ENABLED=true`: dashboard second load is fast; creating a ticket
   updates the totals (invalidation).
4. Redis down: pages/dashboard still load (DB fallback).

---

# HelpDesk — Universal Staff Messaging & @Mentions Review

**Date:** 2026-11-22
**Branch:** `feat/universal-staff-mentions`
**Base:** `main` @ `819a765` (after PR #29)
**Companion report:** [`docs/universal-staff-messaging-mentions-report.md`](docs/universal-staff-messaging-mentions-report.md)
**Verdict:** **IMPLEMENTED AND CI VERIFIED — AWAITING MERGE** (not deployed).

> **Document preservation.** The ticket-pagination review and everything beneath
> it follow verbatim. This review is prepended.

---

## Part A — Repository and remote state

| Item | Finding |
| --- | --- |
| `main` HEAD at start | `819a765` — merge of PR #29 (pagination) |
| `origin/main` | matches `main` @ `819a765` |
| Prior feature branches | width/motion and pagination both **merged**; no in-progress production work |
| Untracked at start | harness files only (`harness.html`, `harness-*.tsx`, `vite.harness.config.ts`) |
| `data.md` | found emptied locally; restored from `HEAD` before prepending this review |
| New branch | `feat/universal-staff-mentions` |

No other branch was overwritten. A separate worktree was unnecessary because the
prior features were already merged and only untracked harness files existed.

---

## Part B — Existing architecture findings

- `staff_conversations` stored a fixed `(staff_user_id, owner_user_id)` pair with
  a **unique index on `staff_user_id`**, so only staff ↔ Owner threads were
  possible. The router even rejected Owner-started conversations.
- `staff_messages.read_at` = the recipient's read state; summaries were already
  N+1-safe and were preserved.
- `internal_messages` / `internal_message_recipients` = Owner compose with
  per-recipient read state.
- The staff directory (`/internal-messages/recipients`) was **Owner-only**.
- No mention capability existed anywhere.
- `staff_dependency` already allowed AGENT/ADMIN/OWNER; the restrictions were in
  the start logic and the directory dependency.

---

## Part C — New universal model

- Generalised `staff_conversations`: `participant_a_id` / `participant_b_id`,
  always written in **canonical (ascending UUID) order**, with a unique pair
  constraint and a `a <> b` check. Any two eligible staff can now converse; the
  pair maps to exactly one thread regardless of who starts it.
- `GET /staff-messages/directory` is now available to every staff role (customer
  403) and returns active AGENT/ADMIN/OWNER accounts excluding the caller.
- Case-insensitive, `@`-prefix-tolerant search over name, username and account id
  with exact-username-first ranking. Verified in-browser that `@A` and `@a`
  return the same employees.

---

## Part D — Structured mentions

- New tables `staff_message_mentions` and `internal_message_mentions`
  (`message_id`, `mentioned_user_id` → `users.id`, unique per pair).
- The body keeps the readable `@username`; the send payload carries
  `mentioned_user_ids` (real ids). Backend validates existence, active status,
  staff role, and not-self; invalid mentions abort the send with `422`.
- Duplicate mentions of one person in a message are stored once.
- The frontend drops a structured mention if its `@username` is edited out.

---

## Part E — Notifications

- New `STAFF_MENTION` notification type on the existing enum, in the existing
  `MESSAGE_TYPES` category and frontend icon/type maps.
- Created only in the same transaction as the persisted message (never on
  typing); the recipient/sender are resolved server-side.
- Exactly one notification per message per person: the recipient/counterpart
  gets one alert, typed `STAFF_MENTION` if mentioned, otherwise the plain
  message type. A mentioned person who cannot open the message (a third party in
  a 1:1 thread, or an unaddressed broadcast recipient) is not notified — the
  mention row is still stored, but no broken/privacy-leaking deep link is sent.
- Customers are never notified about internal mentions.

---

## Part F — Reusable composer & UI

- `StaffMentionComposer` (conversation panel) and `MentionBodyEditor` (Owner
  compose) share `lib/mentions.ts` + `useStaffDirectory`.
- `StaffConversationPicker` + `StartConversationDialog` are shared by the
  agent/admin workspace and the Owner inbox, so every staff role can start a 1:1.
- Accessible combobox pattern (roles/aria-expanded/aria-controls/
  aria-activedescendant), ArrowUp/Down, Enter/Tab to select, Escape to close,
  Enter sends only when the panel is closed, pointer selection with caret
  restoration, `onMouseDown` prevented so focus stays in the composer.

---

## Part G — Migration

`0012_staff_mentions` renames the pair columns, canonicalizes existing rows
(`a < b`; impossible to collide because the old per-staff unique index
guaranteed distinct participants), swaps the index for a unique pair
constraint + check, creates the two mention tables, and appends the
`STAFF_MENTION` enum label. Downgrade restores the columns/constraints and drops
the new objects. Verified **upgrade → downgrade → upgrade** on a disposable
PostgreSQL 18 with a seeded legacy row and no data loss. No Neon migration was
run.

---

## Part H — Tests and results

- Backend: ruff / ruff-format / pyrefly clean; **571 passed, 65 skipped**.
  New `tests/test_staff_mentions.py` (24) + rewritten `tests/test_staff_messages.py`
  (21) cover the full role matrix, directory search (case/prefix/id), mention
  persistence/validation/dedupe, notification dedupe, participant isolation,
  spoofing rejection and customer exclusion.
- Frontend: typecheck + lint pass; **224 passed / 22 files**; build pass. New
  `lib/mentions.test.ts` (18) and `StaffMentionComposer.test.tsx` (10).
- Browser (Playwright, 1366px): `@`, `@A`, `@a` opened the correct suggestions;
  selection inserted `@<username> `; Owner "New message" opened the picker.

---

## Part I — Delivery

- Branch: `feat/universal-staff-mentions`
- Commits: `38fddca`, `37760e7`
- PR: https://github.com/mdjayedgazi/HelpDesk/pull/30 (targets `main`)
- CI: **all checks pass**, including the Alembic migration and PostgreSQL
  integration jobs
- Deployment: **none**. Touches both `helpdesk-api` and `helpdesk-web` and
  requires migration `0012_staff_mentions`, which Railway runs through its
  approved pre-deploy migration step after merge. No Neon or Railway change was
  made from this branch.

### Post-deployment checklist

1. `/health/ready` 200; `alembic current` = `0012_staff_mentions`.
2. Directory works for staff, `403` for customers.
3. Agent ↔ admin ↔ owner conversations all send/receive.
4. `@` works in conversations and Owner compose; active staff only.
5. One notification per mentioned employee; no duplicate for the counterpart.
6. Existing conversations/messages intact.

---

# HelpDesk — Ticket Pagination Continuity Review

**Date:** 2026-11-22
**Branch:** `fix/ticket-pagination-continuity`
**Base:** `main` @ `7a3f9f4` (after PR #28)
**Companion report:** [`docs/ticket-pagination-fix-report.md`](docs/ticket-pagination-fix-report.md)
**Verdict:** **FIXED — CI PASSING, AWAITING PR MERGE** (not deployed).

> **Document preservation.** The UI width/motion review and the Live Neon
> Database Population review beneath it follow verbatim. This review is
> prepended.

---

## Part A — Repository and remote state

| Item | Finding |
| --- | --- |
| `main` HEAD at start | `7a3f9f4` — merge of PR #28 (width/motion) |
| `origin/main` | matches `main` @ `7a3f9f4` |
| Prior feature branch | `feat/helpdesk-ui-width-motion-polish` **merged**; no uncommitted production work |
| Untracked at start | harness files only (`harness.html`, `harness-*.tsx`, `vite.harness.config.ts`) |
| New branch | `fix/ticket-pagination-continuity` (created from clean `main`) |

No other branch was overwritten and no previous work was discarded. A separate
worktree was unnecessary because the previous feature was already merged and the
only local changes were untracked, non-shipping harness files.

---

## Part B — Versions and architecture

| Area | Finding |
| --- | --- |
| Backend | FastAPI 0.162, SQLModel/SQLAlchemy 2.1, Pydantic v2; async SQLAlchemy |
| Frontend | React 19.3, TypeScript ~6.0, Chakra UI 3.37, TanStack Query 5.104 |
| Ticket list endpoints | `GET /api/v1/tickets`, `GET /api/v1/tickets/assigned` |
| Pagination style | offset (`limit`/`offset` originally) — **retained**, fixed |
| Shared component | `src/components/Pagination.tsx` used by tickets, notifications, users, owner inbox |

---

## Part C — Reproduction (evidence)

A disposable PostgreSQL 18 database was seeded with the shape that bulk seeding
produces (a large block sharing one `created_at`, plus a small newer block) and
walked with the shipping query:

```
page 1: 10 rows   page 2: 10 rows   page 3: 10 rows
page 4: 10 rows   page 5:  5 rows   page 6: 0 rows
rows fetched: 45   unique: 30   duplicates: 15
```

45 tickets, only 30 distinct returned, 15 duplicated — the "missing rows +
duplicate rows + empty/gapped pages + invalid trailing page" report, reproduced.

---

## Part D — Root cause

1. **No unique tie-breaker.** `ORDER BY created_at DESC` is not a total order;
   tied timestamps let PostgreSQL reorder rows between `OFFSET` queries →
   duplicates and gaps. SQLite hid this in tests; PostgreSQL exposed it (the
   real deployment).
2. **No total in the response.** The API returned a bare list; the UI guessed
   `hasNext = len == pageSize`, which is wrong for a partial last page and let
   the UI walk past the end.
3. **Client-side filtering after pagination.** `/tickets?assignee=none` filtered
   the already-paginated page, so a full page could render empty while
   unassigned rows existed later.
4. **Duplicated page math.** `limit`/`offset` were computed client-side.

---

## Part E — Backend changes

- `services/tickets.py`: `ticket_list_conditions` (single WHERE builder for data
  **and** count), `count_tickets`, `paginate_tickets`
  (`created_at DESC, id DESC`).
- `schemas/tickets.py`: `TicketPage` envelope
  `{items,total,page,page_size,total_pages,has_next,has_previous}`.
- `routers/tickets.py`: both list endpoints now accept `page`/`page_size`
  (validated `page>=1`, `page_size 1..100`), derive the offset server-side,
  compute `total`/`total_pages`/`has_next`/`has_previous`, and support
  `unassigned=true` as a real SQL filter. Filtering runs before the window; the
  count uses the same conditions as the data query.

Response shape change note: `items` keeps the exact `TicketRead` shape; only the
outer container changed from `[...]` to `{items:[...], …}`. All backend and
frontend consumers were updated, and existing tests were adjusted to read
`["items"]` (not weakened).

---

## Part F — Frontend changes

- `lib/types.ts`: `TicketPage`, and `TicketListParams` now uses
  `page`/`page_size`/`unassigned`.
- `hooks/useTickets.ts`: return `TicketPage` for both list hooks.
- `lib/pagination.ts` (new, pure): `clampPage`, `nextPage`, `previousPage`,
  `canPaginate`, `pageWindow`, `pageRange`.
- `components/Pagination.tsx`: circular Next/Previous in "full mode"; renders
  only valid page numbers (moving window + ellipses); `aria-current="page"`,
  accessible labels, disabled state while loading or single-page; keeps a
  "legacy mode" for the notification/user/inbox lists whose endpoints still
  return bare lists (so those are unaffected).
- `components/TicketListPanel.tsx`: takes `tickets` + optional `pagination`
  metadata; dashboards render static worklists without pagination.
- `pages/TicketsPage.tsx`: server-driven `page`/`page_size`; filters reset page
  to 1; reconciles an out-of-range page against the fresh `total_pages`;
  `assignee=none` → `unassigned=true`.
- `AgentQueuePage`: unassigned tab now uses the server-side `unassigned=true`
  filter (exact totals). Dashboards/AccountRequests read `data.items`.

---

## Part G — Circular navigation

| From | Action | To |
| --- | --- | --- |
| 1 | Previous | last |
| 1 | Next | 2 |
| last-1 | Next | last |
| last | Next | **1** |
| last | Previous | last-1 |

0/1 page disables both controls. Navigation is suppressed while a request is in
flight, so rapid clicks cannot request an invalid page.

---

## Part H — Real-browser verification

Local harness, 300 tickets @ 20/page:

```
PAGES WALKED: 15 · EMPTY INTERMEDIATE: 0 · SHORT INTERMEDIATE: 0
WRAPPED TO 1: true · ROWS: 300 · UNIQUE: 300
NEXT FROM LAST -> Page 1 of 15
```

Partial final page (305 tickets): Previous from page 1 → Page 16 of 16
("Showing 301-305 of 305"); Next → Page 1 of 16. No console errors.

---

## Part I — Quality checks

| Check | Result |
| --- | --- |
| Backend `ruff check` / `ruff format --check` | pass |
| Backend `pyrefly check` | 0 errors |
| Backend `pytest` | **544 passed, 65 skipped** |
| Backend PG integration | **10 passed** against disposable Postgres (incl. new pagination test) |
| Frontend `typecheck` | pass |
| Frontend `lint` | pass |
| Frontend `npm test` | **196 passed / 20 files** (was 174 / 19) |
| Frontend `build` | pass |

New tests: `tests/test_ticket_pagination.py` (23), a PG integration test,
`src/lib/pagination.test.ts` (pure), `src/components/Pagination.test.tsx`,
plus TicketsPage pagination integration cases.

---

## Part J — Delivery status

- Branch: `fix/ticket-pagination-continuity`
- Commit: `613dd61`
- PR: https://github.com/mdjayedgazi/HelpDesk/pull/29 (targets `main`)
- CI: **all checks pass**, including the PostgreSQL integration job
- Deployment: **none**. Touches **both** `helpdesk-api` and `helpdesk-web`;
  they must deploy together (frontend expects the envelope). No migration. No
  Neon data was modified.
- Railway deploys `main` automatically with Wait-for-CI; no merge or manual
  trigger was performed.

### Post-deployment checklist

1. `/health/ready` (API) and `/healthz` (web) OK.
2. `/api/v1/tickets?page=1&page_size=20` returns the envelope.
3. Walk all pages: no empty intermediate page; last page may be partial; Next on
   last → page 1; Previous on 1 → last.
4. Filter/search/page-size changes reset to page 1 with matching totals.
5. `/queue` unassigned totals are exact.

---

# HelpDesk — UI Width, Motion & Premium Interaction Review

**Date:** 2026-11-22
**Branch:** `feat/helpdesk-ui-width-motion-polish`
**Base:** `main` @ `5a379d9` (merge of PR #27)
**Companion report:** [`docs/ui-width-motion-polish-report.md`](docs/ui-width-motion-polish-report.md)
**Verdict:** Frontend-only refinement complete; all checks green; **awaiting review
and merge — not deployed**.

> **Document preservation.** The Live Neon Database Population review and the
> owner-identity, demo-dataset and PR reviews beneath it follow verbatim. This
> review is prepended.

---

## Part A — Repository and remote state

| Item | Finding |
| --- | --- |
| `main` HEAD at start | `5a379d9` — merge of PR #27 (populate Neon demo data) |
| `origin/main` | matches local `main` @ `5a379d9` |
| Feature branch | `feat/helpdesk-ui-width-motion-polish` (existing local branch was at `main`; reused) |
| Open PRs at start | none affecting this work |
| Uncommitted at start | `data.md` modified (emptied); harness files untracked |
| `data.md` | restored from `HEAD` before prepending this review |

The branch was confirmed to share its merge base with `main` at `5a379d9`
(`git merge-base`), i.e. it was a clean starting point, not an older divergent
branch. No other branch was overwritten.

---

## Part B — Versions and stack (verified from `package.json` + lockfile)

| Area | Finding |
| --- | --- |
| React | `19.3.1` |
| TypeScript | `~6.0.2` |
| Chakra UI | `@chakra-ui/react` `3.37.0` (v3 API: `SimpleGrid columns={{…}}`, `Tabs.Root`, `Dialog.Root`) |
| Router | `react-router-dom` `7.18.4` |
| Charts | **hand-written SVG** (no chart library) — `DonutChart`, `BarChart`, `TrendChart`, `Sparkline` |
| Animation libs | **none installed** — no `motion`, no `framer-motion` (checked `package.json` and `package-lock.json`) |
| Motion approach | CSS custom-property transitions + `requestAnimationFrame` + `IntersectionObserver` (`Reveal`) |
| Testing | `vite-plus` / Vitest (`vp test`), Testing Library, jsdom |
| Build | `tsc && vp build`; production build validates `VITE_API_URL` + Clerk key |
| Breakpoints | Chakra defaults: sm 30rem, md 48rem, lg 64rem, xl 80rem, 2xl 96rem |

**Important finding:** the brief references the `motion` package APIs. The
project does not use Motion at all and has a deliberate, documented CSS/rAF
motion system. Adding Motion would have been an unnecessary dependency for a
handful of interactions, so the existing system was extended instead. Nothing
here uses outdated `framer-motion` patterns because nothing uses either package.

---

## Part C — The width problem: cause and fix

### C.1 Exact cause

The authenticated shell rendered every page through
`<Container size='content'>`, and `widths.content` was **`1200px`**. On a 1920 px
display the fixed 256 px sidebar leaves a **1664 px** main column, but the
container clamped it to 1200 px and centred it — **232 px of dead space on each
side**. It was not a `50%` rule and not a grid bug; it was one reused cap.

Compounding issues found during measurement:

1. The dashboard composition row was a fixed `lg:3` grid, so at 1024 px three
   chart cards were squeezed to ~177 px of inner width — the "half width" look.
2. The five KPI cards used `lg:5`, giving ~128 px cards at 1024 px.
3. The accessible chart `<table>` (visually hidden) still expanded to its
   intrinsic width and could push the document wider than the viewport.
4. The mobile filter tab strip overflowed horizontally at 390 px.
5. `AccountRequestDetailPage` used Chakra's `container.lg` (~1024 px), not the
   app token, so it floated narrow on wide screens.

### C.2 Measured before → after

| Viewport | Main column | Container before | Container after | Dead space/side before → after |
| --- | --- | --- | --- | --- |
| 1366 | 1110 | 1110 | 1110 | 0 → 0 |
| 1440 | 1184 | 1184 | 1184 | 0 → 0 |
| 1600 | 1344 | 1200 | 1344 | 72 → 0 |
| 1920 | 1664 | 1200 | 1664 | **232 → 0** |

### C.3 Changes

- `theme/layout.ts`: added `widths.workspace = '1680px'` (cap only bites on
  ultra-wide displays), `widths.detail = '1120px'`, and a `workspaceGutter`
  scale (tighter on phones, roomier at 2xl). Marketing `content/wide/reading`
  measures are unchanged.
- `components/Container.tsx`: new `workspace` size using that gutter.
- `components/AppShell.tsx`: `size='content'` → `size='workspace'`.
- `pages/admin/AdminDashboard.tsx`: KPI grid `base:2 → md:3 → xl:5`; composition
  grid `base:1 → md:2 → 2xl:3`.
- `pages/staff/AccountRequestDetailPage.tsx`: `maxW='container.lg'` →
  `widths.detail` + `w='full'`.
- `components/charts/ChartCard.tsx`: clip the outer wrapper, keep the `<table>`
  inside it (stops intrinsic-width overflow).
- `pages/NotificationsPage.tsx`, `pages/agent/AgentQueuePage.tsx`: tab strips get
  `hd-tabs-scroll` + `minW='0'` (contained horizontal scroll, no page overflow).

### C.4 Result

Every route in the sweep now reports **0 horizontal overflow** at 390, 430, 768,
1024, 1280, 1366, 1440, 1600 and 1920 px, and the main column is fully used on
wide displays.

---

## Part D — Data-viz interaction improvements

The charts were not replaced. Their interaction layer was enriched, using only
the real analytics payload.

- **Status donut:** hover **or keyboard focus** on a segment/legend row opens a
  rich panel showing the status name, colour, exact ticket count, share of all
  tickets and a one-line meaning. Verified live: "In progress · 27 tickets · 9%
  of 300 tickets · An agent is actively working on the request."
- **Priority bars:** same rich panel with exact count, share and a meaning line
  ("Urgent · 19 tickets · 6% of 300 tickets · Blocking the requester; handle
  first."). Actionable rows are keyboard reachable; category rows are not put in
  the tab order because their numbers are already printed and mirrored in the
  accessible table.
- **Trend chart:** existing per-day readout (created vs resolved) retained;
  surfacing aligned to the new tooltip styling.
- **Tooltip engine:** `lib/tooltipPosition.ts` (pure, unit-tested) flips and
  clamps the panel inside its host; `chart/ChartTooltip.tsx` renders inside the
  chart wrapper (no portal, no clipping) with `pointer-events:none` (no
  flicker when moving toward it).
- **Narrow-card fix:** the donut measures its own width and stacks the legend
  under the ring below 424 px, fixing a real 0 px legend-label collapse at
  1024 px.

All percentages are computed from the same totals rendered elsewhere on the
page, so the panel, legend, centre label and accessible table cannot disagree.

---

## Part E — Cursor and motion engineering

No library was added; the existing `requestAnimationFrame` + CSS system was
extended.

- **`hooks/usePointerSpotlight.ts`** — a critically-damped spring (stiffness 170,
  damping 26) integrated per-frame, writing CSS custom properties directly to
  the node. Pointer movement causes **zero React renders**. The loop parks itself
  when settled (measured **0 idle rAF/s**) and clears all values on unmount.
- **`components/PointerHighlight.tsx`** — soft radial light painted **above** the
  opaque card (a glow behind an opaque panel would be invisible). ~20% peak of a
  low-alpha accent, faded to nothing at the edge. Applied only to interactive
  metric cards; inert cards get nothing so the affordance is never false.
- **`components/motion/TiltSurface.tsx`** — marketing-only 3D tilt upgraded from
  a fixed CSS easing to the same spring integration (4° cap, fine-pointer and
  ≥1024 px gates, reduced-motion guard all preserved).
- All of the above bail out under `prefers-reduced-motion`, on coarse pointers
  and below 1024 px. Verified in a reduced-motion browser context.

Animation properties are `transform`/`opacity`/custom-property only — no
width/height/top/left churn — so there is no layout thrash.

---

## Part F — Accessibility

- Reduced motion disables the spotlight, the tilt and the new tooltip entrance;
  global CSS already zeroes durations. Confirmed in-browser.
- Tooltips are reachable by keyboard (focus), not hover-only. Confirmed.
- Chart SVGs remain `aria-hidden`; the visually hidden tables carry the data.
- Tooltips are `aria-hidden` because they duplicate data the screen reader
  already has (avoids double announcements).
- Touch: hover effects are gated behind `pointer: fine`; nothing critical
  depends on hover.

---

## Part G — Quality checks (final tree)

| Check | Result |
| --- | --- |
| `npm run typecheck` | pass |
| `npm run lint` | pass |
| `npm test` | **148 passed / 18 files** (baseline was 136 / 16) |
| `npm run build` (CI-style env) | pass |
| Browser overflow sweep (9 widths × 9 routes) | 0 overflow rows (was 3) |
| Console errors on tested routes | none |
| Tooltip containment (390/1024/1280/1366/1920) | fully inside host + viewport |

New tests: `tooltipPosition.test.ts` (6), `usePointerSpotlight.test.tsx` (4),
plus 2 donut cases in `dataAccuracy.test.tsx`. Existing tests were not weakened.

---

## Part H — Delivery status

- Branch: `feat/helpdesk-ui-width-motion-polish`
- Commits: `e6863fb` (implementation) → `d5f10dd`, `f6b874b` (report updates)
- PR: https://github.com/mdjayedgazi/HelpDesk/pull/28 (targets `main`,
  `MERGEABLE`)
- CI: **all checks pass** — Backend lint + SQLite tests, Frontend
  typecheck/lint/tests/build, Alembic migrations, PostgreSQL integration, Docker
  image builds, Production dependency audit, Helm validation, Static security +
  secret scan, CodeQL, Trivy.
- **Deployment: none.** No merge, no production trigger.
- The harness files used for visual verification are **not committed**, so the
  PR is frontend-production-only (26 files, none matching `harness`).

### Verified Railway deployment configuration

From `docs/RAILWAY_COLLEGE_DEMO.md`, `docs/DEPLOYMENT.md` and
`frontend/Dockerfile`:

| Item | Value |
| --- | --- |
| Service | `helpdesk-web` (dashboard-configured; no `railway.toml/json`) |
| Repository root | `/frontend` |
| Build | `frontend/Dockerfile` → `npm ci && npm run build` (`tsc && vp build`) |
| Production branch | `main`, automatic on push |
| CI gate | Wait-for-CI (`checkSuites=true`): required GitHub checks must pass |
| Healthcheck | `/healthz` on container port `8080` (`nginx.conf.template`) |
| Preview deploys | none configured |

Because deployment is automatic on `main` behind Wait-for-CI, merging this PR is
the release trigger — so no merge or manual trigger was performed during this
task.

### Post-deployment checklist (after a future merge)

1. API `/health/ready` → 200 (`database/redis ok`); frontend `/healthz` → `ok`.
2. `/dashboard` at ≥1600 px fills the main column (no ~230 px side gutters).
3. Hovering an "Open" donut segment shows the real count and share.
4. Hovering/focusing a priority bar shows the rich tooltip, unclipped.
5. Card spotlight is subtle and clears on leave; absent under reduced motion.
6. No horizontal scrollbar at 390 px.

---

# HelpDesk — Live Neon Database Population

**Date:** 2026-11-21
**Branch:** `feat/populate-neon-demo-data`
**Target:** live Railway `helpdesk-api` → Neon `neondb`
**Full report:** [`docs/neon-demo-data-population-report.md`](docs/neon-demo-data-population-report.md)
**Verdict:** **SUCCESSFULLY SEEDED AND DATABASE VERIFIED** — the real Neon
database now holds 100 users, 300 tickets and every supported associated entity.
The frontend was verified only at the API/HTTP level (see Part F).

> **Document preservation.** The owner-identity review and, beneath it, the demo
> dataset and PR #19 reviews follow verbatim. This review is prepended.

---

## Part A — Repository and remote state

| Item | Finding |
| --- | --- |
| `main` HEAD at start | `88fd2eb` — merge of PR #26 (owner identity) |
| PR #26 | **MERGED** 2026-11-21T20:35:16Z |
| Open PRs | none |
| `data.md` | found emptied locally; restored from `HEAD` before extending it |
| New branch | `feat/populate-neon-demo-data` |

PR #25 (demo seeding) and PR #26 (owner identity) are both merged, so their code
is on `main` and in the deployed backend.

---

## Part B — Prerequisite check: was the Owner implementation actually live?

The previous report said `OWNER_EMAIL` was *staged, not deployed*. That is **no
longer true**, verified rather than assumed:

| Evidence | Result |
| --- | --- |
| Railway deployment list | `d588d335` **SUCCESS** at `2026-11-21T20:35:18Z` |
| PR #26 merge time | `2026-11-21T20:35:16Z` (2 s earlier) |
| `/health/ready` | 200 — `database: ok, schema: ok, redis: ok` |

The deployed build is the merged `main` commit, which reads `OWNER_EMAIL`.

---

## Part C — Real Owner verification

Read-only inspection of the **only** existing user:

| Property | Value |
| --- | --- |
| Users in database | **1** |
| Role | `OWNER` |
| Active | `true` |
| Has real Clerk ID | `true` |
| Stored email matches configured `OWNER_EMAIL` | **yes** (compared privately) |

No identity was fabricated; the existing account already satisfied the
requirement, so no reconciliation change was needed. Exactly one real Owner.

---

## Part D — Actual database facts

| Property | Value |
| --- | --- |
| PostgreSQL | **18.7** (`server_version_num` 180007) — verified live, not assumed |
| Database / schema | `neondb` / `public` |
| Host (sanitized) | `ep-prou***.c-7.us-east-2.aws.neon.tech` (pooled) |
| Alembic revision | `0011_query_indexes` = repository head (no pending migration) |
| Extensions | `plpgsql` |
| Railway | project `helpdesk-college-demo`, env `production`, services `helpdesk-api` / `helpdesk-web` |

Starting state: all 15 application tables present; every table empty **except
`users`, which held the single real Owner**. So the database was not assumed
empty — it was measured.

**Recovery:** no Neon API key/CLI is available to this session, so no branch was
created. Judged safe because there was no application data to lose and the seeder
is INSERT-only in one transaction. No `DROP`/`TRUNCATE`/`DELETE` was run.

---

## Part E — Execution and results

Dry-run first (no writes), then a **single** production run through the verified
Railway service:

```
railway run --service helpdesk-api --environment production \
  sh -c 'python -m app.commands.seed_demo_data --size 100'
```

Actual inserted rows (one transaction):

| Entity | Inserted |
| --- | ---: |
| users (synthetic) | 99 (→ **100 total** with the Owner) |
| tickets | 300 |
| comments | 789 (100 internal) |
| ticket history | 974 |
| notifications | 525 (587 including admin alerts) |
| staff conversations / messages | 12 / 36 |
| internal messages / recipients | 6 / 62 |
| account requests / comments / events | 12 / 21 / 21 |
| ticket feedback | 34 |
| attachments | 12 |

Distributions matched exactly:

- Roles: `owner 1, admin 8, agent 20, customer 71`.
- Status: `OPEN 60, IN_PROGRESS 60, WAITING 60, RESOLVED 90, CLOSED 30`.
- Priority: `LOW 45, NORMAL 135, HIGH 90, URGENT 30`.
- Assigned 269 / unassigned 31.

`Owner unchanged during seed: True`.

---

## Part F — Verification (all from the live database)

**Analytics vs direct SQL:** identical — 300 tickets, 100 users, 120 open, 90
resolved, 30 closed, 31 unassigned, 29 unassigned >24 h, 24 aging, 20 urgent open,
60 waiting, 18 active agents. 14-day window: **108 created / 49 resolved**, with
activity on **13 of 14** days.

**Integrity (all zero):** non-AGENT assignees, resolved-before-created,
future created, future updated, comment-before-ticket, customer internal notes,
notifications with missing recipients, duplicate emails, duplicate usernames.

**Notifications:** 587 total, 157 unread (26.7%).

**Idempotency:** a second full run inserted **0** rows and reused every entity.

**Frontend / API:** frontend HTTP 200; `/health/live` and `/health/ready` 200;
anonymous `/api/v1/admin/analytics` and `/api/v1/users/me` both **401**, so
authorization is intact.

**Not verified:** signed-in browsing of the Owner dashboard and each workspace
page. That requires a real Clerk Owner session, which this environment cannot
create without fabricating authentication. Those pages are **manual verification**
items; the data and API are confirmed.

---

## Part G — Security compliance

- No `.env` contents, passwords, connection strings, Neon secrets or Clerk keys
  were printed. The database host is shown sanitized only.
- No Clerk identity, `clerk_id`, or Owner account was fabricated.
- No authentication/authorization weakened; anonymous API calls still return 401.
- No database constraints disabled; no destructive SQL.
- No unrelated Railway variables changed and no unrelated deployment triggered.
- No existing application data deleted; the real Owner is preserved.

---

## Part H — Verdict

**SUCCESSFULLY SEEDED AND DATABASE VERIFIED.**

The real Neon database now contains the complete demo dataset, all aggregates are
consistent with direct SQL, every integrity check is clean, exactly one real Owner
exists, and the operation is repeat-safe.

---

## Part Z — Preserved prior reviews

The owner-identity review (PR #26) and, beneath it, the demo-dataset review
(PR #25) and the PR #19 production-readiness review follow verbatim.
# HelpDesk — Configurable Owner Identity & Automatic Ownership Transfer

**Review date:** 2026-11-21
**Repository:** `mdjayedgazi/HelpDesk`
**Branch:** `feat/configurable-owner-email` (new, from `main` @ `917af4b`)
**Companions:** [`docs/owner-identity-endpoint-audit.md`](docs/owner-identity-endpoint-audit.md),
[`docs/owner-identity-implementation-report.md`](docs/owner-identity-implementation-report.md),
[`docs/owner-identity-operations.md`](docs/owner-identity-operations.md)
**Verdict:** Implemented and tested. The Railway production variable is
**staged, not active** — the behaviour goes live only when this branch merges and
Railway deploys it.

> **Document preservation.** The previous review (demo dataset) occupies the rest
> of this file, and the PR #19 production-readiness review beneath that, both
> verbatim. This task's review is prepended, not substituted.

---

## Part A — Repository and remote state at the start

| Item | Finding |
| --- | --- |
| `main` HEAD | `917af4b` — merge of PR #25 (demo seeding) |
| Open PRs | none |
| Merged PRs | #19, #20, #21, #22, #23, #24, #25 |
| Existing owner implementation | `app/commands/bootstrap_owner.py`, `INITIAL_ADMIN_EMAIL` |
| Existing feature branches | `feat/demo-dataset-seeding`, `feat/helpdesk-motion-visual-polish`, `feat/helpdesk-ui-ux-modernization` — all merged; none reused |
| New branch | `feat/configurable-owner-email` |
| `gh auth` | authenticated as `mdjayedgazi` (`repo`, `workflow`) |
| `data.md` | found emptied locally; restored from `HEAD` and extended with this review |

---

## Part B — Audit findings that shaped the design

1. **`INITIAL_ADMIN_EMAIL` was bootstrap-only.** Its own docstring says it is
   "never consulted on the request path". The brief needs a canonical setting that
   also drives recognition and transfer, so `OWNER_EMAIL` was added as the
   authority with the legacy variable as a fallback.
2. **One synchronisation point.** `app/core/auth.py::get_current_user` is the only
   code that provisions or links users. That is the correct single place for
   recognition, so signup and every later sign-in share it.
3. **No webhook exists.** Registration is synchronised synchronously on the first
   authenticated request. No new webhook was added; the existing reliable path was
   used.
4. **`bootstrap_owner` could not transfer.** It refuses when an Owner exists, so
   it can never be the transfer mechanism. It was re-pointed at the shared service
   but kept its initial-setup role.
5. **Single-Owner is a database invariant.** `uq_users_single_owner` is a partial
   unique index; every change must be one transaction that never shows two Owners.

The full endpoint inventory (30 endpoints, with auth/authorization/role-impact
columns) is in `docs/owner-identity-endpoint-audit.md`.

---

## Part C — Configuration

`OWNER_EMAIL` is added to `backend/app/core/config.py`. Resolution order:

1. `OWNER_EMAIL` (trimmed, lowercased);
2. deprecated `INITIAL_ADMIN_EMAIL` when `OWNER_EMAIL` is unset;
3. else `None` — automatic recognition disabled.

`owner_email_conflict` reports (as a boolean only) whether both are set to
different addresses; `OWNER_EMAIL` still wins. No property or log line ever
returns an address.

`backend/.env.example` contains the placeholder `OWNER_EMAIL=owner@example.com`
and marks `INITIAL_ADMIN_EMAIL` deprecated. **The real address appears in no
tracked file** (verified by grep across `backend/`, docs and the diff).

---

## Part D — Implementation

### D1. One shared algorithm — `app/services/owner_identity.py`

| Function | Role |
| --- | --- |
| `normalize_email` | the single comparison convention |
| `evaluate` | pure decision (no writes, no I/O beyond a Clerk read) |
| `reconcile_owner` | atomic promotion/transfer, locked |
| `find_candidate_by_email` | normalized lookup of the designated account |

Callers: request path, startup, `reconcile_owner` command, and `bootstrap_owner`.
There is no second promotion path.

### D2. Request-path recognition

`get_current_user` calls `_reconcile_owner_for` for (a) an existing local user and
(b) a freshly provisioned/linked user (reusing the Clerk object already fetched).
It is a no-op unless `OWNER_EMAIL` is set and the verified primary email matches.

### D3. Deployment reconciliation

- `lifespan` performs one best-effort reconciliation before readiness; a missing
  account or Clerk outage logs a sanitized warning and never fails boot.
- `python -m app.commands.reconcile_owner` is the operator/deploy command
  (`--json` supported). Exit codes: `0` safe/no-op, `2` no config, `1` a genuine
  transaction failure (rolled back).

### D4. Bootstrap preserved

`bootstrap_owner` keeps "refuse if an Owner exists" and now delegates the actual
promotion to `reconcile_owner`, so the two can never diverge.

---

## Part E — Clerk verification (security core)

Promotion requires **all** of: a Clerk identity from the trusted token `sub`; a
successful `clerk.users.get_async`; a `primary_email_address_id` whose
verification status is `verified`; that normalized address equal to
`OWNER_EMAIL`; and an active local account.

Explicitly rejected: form-supplied email, client-supplied role, secondary email,
unverified email, Clerk metadata, cached local email. Clerk being unreachable
yields `identity_unavailable` and changes nothing.

---

## Part F — Transaction and locking

`reconcile_owner`:

1. `pg_advisory_xact_lock` (key `20261122`) — transaction scope;
2. target and previous Owner selected `FOR UPDATE`;
3. **demote previous → ADMIN and flush**, then promote target and flush;
4. one commit, full rollback on any error.

SQLite skips the lock; the partial unique index is the final guarantee.

---

## Part G — Previous Owner behaviour

Role becomes `ADMIN`. The row is otherwise untouched: `is_active` stays true,
`clerk_id` unchanged, tickets/comments/notifications/feedback/conversations
untouched. `ADMIN` retains administrative access but loses Owner-exclusive
abilities (role/status management, Owner broadcasts). Deletion and deactivation
never happen automatically; deactivation is a separate, reversible Owner action.

---

## Part H — Tests actually executed

| Suite | Result |
| --- | --- |
| Full backend suite (`pytest -q`) | **521 passed**, 64 skipped (opt-in PG/Redis) |
| `tests/test_owner_identity.py` (SQLite + Clerk doubles) | 33 passed |
| `tests/test_owner_identity_postgres.py` (disposable PG 16) | 6 passed |
| `ruff check` / `ruff format --check` | clean (121 files formatted) |

Coverage highlights:

- **Configuration:** unset, whitespace, case, empty, legacy fallback, precedence,
  conflict flag, and that no address is exposed.
- **Recognition:** verified primary match, verified-but-different, unverified,
  secondary-only, Clerk failure, inactive, no-config, missing local account,
  case/whitespace insensitivity.
- **Ownership:** promotion, already-owner idempotency, transfer with previous
  Owner → ADMIN, unrelated users and ticket/comment data preserved, repeated
  reconciliation producing no second transfer.
- **Security:** customer/agent/admin escalation attempts, `owner` rejected as an
  assignable role, Owner cannot assign OWNER to another, unverified promotion
  attempt, Clerk failure at the request path.
- **PostgreSQL:** real partial index present, promotion, transfer leaves one
  Owner, **five concurrent reconciliations converge to one Owner**, forced failure
  rolls back, transfer preserves tickets and comments.
- **Operational:** reconcile command no-config → 2, unregistered target → 0
  (non-fatal), startup hook never raises on a broken database.

---

## Part I — Railway production configuration

Verified with the authorised CLI (`railway whoami` confirmed the account; I did
not re-run it because it echoes the owner's address).

| Item | Value |
| --- | --- |
| Project | `helpdesk-college-demo` |
| Environment | `production` |
| Backend service | `helpdesk-api` |
| Frontend service | `helpdesk-web` |
| Variable count before | 27 |
| Variable count after | 28 |
| `OWNER_EMAIL` set | yes (value compared privately; matches the designated address) |
| `INITIAL_ADMIN_EMAIL` | absent (no legacy value to reconcile) |
| Other variables changed | none (DATABASE_URL, CLERK_SECRET_KEY, ENVIRONMENT, DEPLOYMENT_PROFILE, ATTACHMENTS_ENABLED all still present) |
| Frontend variables | unchanged; `OWNER_EMAIL` **not** added (19 keys, no OWNER_EMAIL) |
| Deploy triggered | **no** — set with `--skip-deploys` |

The value was supplied on stdin so it never appeared in the command line or the
output. No secret was printed.

---

## Part J — Activation status

**Staged, not deployed.** The variable is stored on `helpdesk-api`/`production`,
but the running backend is still the previous `main` build, which does not read
`OWNER_EMAIL`. Verification:

- live `GET /health/live` → **200** (service healthy, unchanged);
- `OWNER_EMAIL` support exists only on this branch (`backend/app/core/config.py`);
- no deployment was triggered (`--skip-deploys`).

Ownership recognition becomes live only when this PR is merged to `main` and
Railway deploys that merged commit.

---

## Part K — API regression

The 488 pre-existing tests continued to pass before the new owner tests were
added (final count 521). The only request-path behaviour change is that an
account matching `OWNER_EMAIL` with a verified primary email becomes Owner; all
other roles and endpoints are unchanged. The frontend already refetches
`GET /api/v1/users/me`, so a promoted role is reflected on the next fetch with no
frontend change.

---

## Part L — Limitations (stated plainly)

1. **No live production verification.** Behaviour is proven by tests, not by
   signing in as the designated Owner on production — that requires the merge and
   deploy, which this task explicitly must not trigger.
2. **The designated person must register and verify** before recognition. Until
   then the previous Owner is preserved by design.
3. **SQLite cannot prove concurrency**, hence the PostgreSQL suite; the
   advisory-lock code path only executes on PostgreSQL.
4. **`--skip-deploys` means the staged variable is inert** until a real deploy.
5. **The `railway whoami` output echoed the owner's email** in the terminal
   (Railway's own CLI behaviour). No secret (key, password, URL) was printed, and
   no address was written to any tracked file. Consider rotating only if terminal
   history is retained and considered sensitive.

---

## Part M — Delivery checklist

| Requirement | Status |
| --- | --- |
| Canonical `OWNER_EMAIL` setting | done |
| Verified Clerk primary email only | done |
| Automatic recognition on signup/sync | done |
| Automatic transfer after address change | done |
| Previous Owner → ADMIN, data intact | done |
| Exactly one Owner guaranteed | done (partial index + lock) |
| Signup and sync share one algorithm | done |
| Idempotent deployment reconciliation | done |
| Railway `helpdesk-api`/`production` variable | set (staged, `--skip-deploys`) |
| Tests pass | 521 backend + 6 PG |
| Separate branch | `feat/configurable-owner-email` |
| Open PR | see the hand-off (PR number/URL) |
| No merge, no force-push, no deploy | honoured |

---

## Part Z — Preserved prior reviews

The demo-dataset review (PR #25) and, beneath it, the PR #19 production-readiness
review follow verbatim.
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
