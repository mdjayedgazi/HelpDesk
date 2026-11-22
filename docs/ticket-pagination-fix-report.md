# HelpDesk — Ticket Pagination Fix Report

- **Date:** 2026-11-22
- **Branch:** `fix/ticket-pagination-continuity`
- **Base:** `main` @ `7a3f9f4` (after PR #28 merged)
- **PR target:** `main`
- **Scope:** backend (`GET /api/v1/tickets`, `GET /api/v1/tickets/assigned`) and
  its frontend consumers. No database migration, no seed change, no data
  mutation.
- **Verdict:** **FIXED — CI PASSING, AWAITING PR MERGE** (see §14 for the
  evidence-based reasoning and the deployment note).

---

## 1. Original reproduction

Observed by the reporter on the real seeded database (300 tickets): repeatedly
clicking Next showed some full pages, some **empty intermediate pages**, later
pages with data again, and an **invalid trailing page** that contained nothing —
while Next kept advancing.

Reproduced locally against a **disposable PostgreSQL 18** database with a
dataset shaped like real bulk-seeded data (a large block of tickets sharing one
`created_at`, plus a small newer block), walking pages with the shipping query:

```
page 1: 10 rows
page 2: 10 rows
page 3: 10 rows
page 4: 10 rows
page 5:  5 rows
page 6:  0 rows
rows fetched: 45   unique: 30   duplicates: 15
distinct tickets in DB: 45; fetched unique: 30
```

That is the bug in one line: **45 tickets, but a full walk returned only 30
distinct tickets and 15 duplicates.** On the real app this manifests as rows
appearing twice and others never appearing, with gaps at the page boundaries.

---

## 2. Exact root cause

Three independent defects combined:

1. **Non-deterministic ordering (the core bug).**
   `GET /tickets` used `ORDER BY tickets.created_at DESC` with no unique
   tie-breaker. `created_at` is **not unique** — bulk seeding, batch imports and
   any two writes in the same timestamp produce ties. PostgreSQL does not
   guarantee a stable physical order for tied rows across separate `OFFSET`
   queries, so page N and page N+1 could overlap (duplicates) while other tied
   rows were never returned (silent gaps). SQLite happened to return a stable
   order, which is why the defect only appeared on the real PostgreSQL database.

2. **No total / guessed "has next".**
   The endpoint returned a **bare list** with no `total`. The frontend inferred
   `hasNext = items.length === pageSize`. That is wrong for a partial last page
   (the UI still offered Next) and it let the UI request page N+1 forever, each
   time with an offset past the real end — the "invalid final page".

3. **Filtering after pagination.**
   The "unassigned" view (`/tickets?assignee=none`) was filtered **client-side
   after** the server had already applied `LIMIT/OFFSET`. A page could arrive
   full of assigned tickets that the client then removed, producing an
   apparently empty page while unassigned rows existed later — with a page count
   that described the unfiltered set.

A fourth, smaller issue: `limit`/`offset` were passed through by the client, so
the page arithmetic lived in two places and could drift.

---

## 3. Affected frontend components

- `src/pages/TicketsPage.tsx` — builds query params, owns page state.
- `src/components/TicketListPanel.tsx` — renders the table + pagination.
- `src/components/Pagination.tsx` — the controls.
- `src/hooks/useTickets.ts` — `useTickets`, `useAssignedTickets`.
- `src/lib/types.ts` — `TicketListParams`, new `TicketPage`.
- Consumers of the list query: `AgentQueuePage`, `AgentDashboard`,
  `CustomerDashboard`, `AccountRequestsPage`.

---

## 4. Affected backend endpoints and query functions

- `GET /api/v1/tickets` → `app/api/routers/tickets.py::list_tickets`
- `GET /api/v1/tickets/assigned` → `list_my_assigned_tickets`
- New shared helpers in `app/services/tickets.py`:
  - `ticket_list_conditions(...)` — one WHERE builder for data **and** count.
  - `count_tickets(...)` — count over the exact same conditions.
  - `paginate_tickets(...)` — deterministic, windowed data query.
- New response schema `app/schemas/tickets.py::TicketPage`.

---

## 5. Corrected counting and offset logic

- Filters are applied **before** the window; the `COUNT(*)` query is built from
  the **same** `conditions` list as the data query, so `total` can never
  disagree with the page contents.
- `page` is one-based and `page_size` is the row count; the offset is derived
  **server-side** as `(page - 1) * page_size`, removing duplicate page math.
- `total_pages = max(1, ceil(total / page_size))` — a zero-result set reports
  exactly one (empty) page, never zero.
- `has_next = page < total_pages`, `has_previous = page > 1` — explicit
  booleans derived from the true total, not from page length.
- Query validation: `page >= 1`, `page_size` in `[1, 100]` (FastAPI `Query`
  constraints return `422` for `page=0`, negative pages, `page_size=0` or
  `>100`).
- `unassigned=true` is now a real server-side filter (`assignee_user_id IS
  NULL`), so pagination and `total` describe the same set.

---

## 6. Stable ordering strategy

`ORDER BY tickets.created_at DESC, tickets.id DESC`.

The primary key is unique, so `(created_at, id)` is a **total order**: every row
has exactly one position, independent of the planner's physical access path.
The requested "newest first" ordering is preserved; the id only breaks ties.

A structural unit test compiles the SQL and asserts the `ORDER BY` clause is
`created_at DESC` followed by `id DESC` (see §9), so the guarantee cannot
silently regress even if PostgreSQL's statistics make an execution-only test
pass by luck.

---

## 7. Circular navigation behavior

Implemented in the pure module `src/lib/pagination.ts` and rendered by
`Pagination`:

| Current page | Action | Destination |
| --- | --- | --- |
| 1 | Previous | last page (`totalPages`) |
| 1 | Next | 2 |
| 5 | Next | 6 |
| total-1 | Next | total |
| total | Next | **1** |
| total | Previous | total-1 |

- For 0 or 1 page, Next and Previous are **disabled** (`canPaginate`).
- Only real page numbers are rendered, via a moving window with ellipses
  (`pageWindow`), always including page 1 and `totalPages`.
- Navigation is suppressed while a page request is in flight (`isLoading`), so
  rapid clicks cannot queue invalid pages.

---

## 8. Filter and search behavior

- `page` resets to **1** whenever the search term, status, priority or assignee
  changes (effects in `TicketsPage`).
- The search term is debounced and written to the URL; the URL remains the
  source of truth for filters, so deep links and back/forward still work.
- If records are deleted while the user is on a high page, the response's
  `total_pages` shrinks; the page is **reconciled** back to the last valid page
  instead of showing an empty page with missing data.
- The query key already includes the full params object, so page/filter changes
  are separate cache entries; `keepPreviousData` keeps the previous table
  visible during the transition while navigation is disabled.

---

## 9. Regression tests

### Backend — `tests/test_ticket_pagination.py` (23 tests)

First/second/middle/last/partial-last pages; zero records; exactly one page;
multiple full pages walked without gaps or duplicates; **empty-intermediate-page
regression with tied timestamps**; newest-first ordering; invalid page and page
size rejected; out-of-range page is well-formed; search + pagination; status,
priority, category filters + pagination; server-side `unassigned` + pagination;
assignee filter + pagination; role visibility + pagination; agent
assigned+unassigned visibility; assigned endpoint envelope; different page sizes
cover the same set; created_at ties use the id tie-breaker across pages; total
matches the count query not the page length; effective page size in the
envelope; **structural ORDER BY guarantee**.

### Backend — `tests/test_postgres_integration.py`

`test_pagination_is_gap_free_on_real_postgres`: builds a tied+newer dataset on
real PostgreSQL, walks **past** the reported last page (as the buggy UI did),
and asserts every ticket is returned exactly once. Runs only against a
disposable database (guarded by `_disposable_db_guard`).

### Frontend

- `src/lib/pagination.test.ts` (pure): Next/Previous wrap, clamping, `canPaginate`,
  window validity (never out of range, ellipses only for gaps), page ranges.
- `src/components/Pagination.test.tsx`: circular Next/Previous at the component
  boundary, valid page numbers only, `aria-current`, page-number click,
  single-page/empty disabled, loading suppression, current-page no-op, legacy
  mode.
- `src/pages/TicketsPage.test.tsx`: page 1 + page size on load, Next advances,
  wrap last→1, wrap 1→last, status/search reset to page 1, out-of-range
  reconciliation, never requesting a page beyond `total_pages`.

Existing backend tests were updated only for the new envelope shape
(`response.json()["items"]`); none were weakened.

### Real-browser verification

Against the local harness (300 seeded-shaped tickets, 20/page):

```
PAGES WALKED: 15
page 1:  Showing 1-20 of 300 (20 rows)
...
page 15: Showing 281-300 of 300 (20 rows)
EMPTY INTERMEDIATE: 0
SHORT INTERMEDIATE (before last): 0
WRAPPED TO 1: true
TOTAL ROWS COLLECTED: 300  UNIQUE: 300
NEXT FROM LAST -> Page 1 of 15
```

Partial-final-page case (305 tickets): page 1 of 16 shown; Previous from page 1
→ **Page 16 of 16, "Showing 301-305 of 305"**; Next → **Page 1 of 16**.

---

## 10. Responsive and accessibility checks

- Pagination wraps on narrow screens; the page-number window scrolls within its
  own strip (`hd-tabs-scroll`) rather than widening the document.
- Every control has an `aria-label` ("Next page", "Previous page", "Page N");
  the current page carries `aria-current="page"`.
- Disabled state is expressed with the real `disabled` attribute (not just
  styling), so keyboard and screen-reader users get the correct affordance.
- No horizontal overflow: the layout keeps the existing table wrapper's
  responsive behaviour; no redesign was done.
- Reduced-motion and color/typography are untouched (no new animation added).

---

## 11. Actual CI results

All PR checks pass, including the dedicated **PostgreSQL integration** job
(which runs the real-database pagination regression). Reported checks:
Backend lint + SQLite tests, Frontend typecheck/lint/tests/build, Alembic
migrations, PostgreSQL integration, Docker image builds, Production dependency
audit, Helm validation, Static security + secret scan, CodeQL, Trivy.

Locally, on the final tree:

- Backend: `ruff check` pass, `ruff format --check` pass, `pyrefly check` 0
  errors, `pytest` **544 passed, 65 skipped** (607 including the opt-in PG
  module when pointed at a disposable database: +10 passed).
- Frontend: `npm run typecheck` pass, `npm run lint` pass, `npm test` **196
  passed / 20 files**, `npm run build` (CI-style env) pass.

---

## 12. Git branch and commit

- Branch: `fix/ticket-pagination-continuity` (from `main` @ `7a3f9f4`; the prior
  width/motion work was already merged, so the tree started clean apart from the
  untracked verification harness).
- Implementation commit: `613dd61` — `fix(tickets): make pagination
  deterministic and add circular navigation`.

---

## 13. PR URL

**https://github.com/mdjayedgazi/HelpDesk/pull/29** (targets `main`, all checks
passing).

---

## 14. Deployment status

**Not deployed. Awaiting review and merge.**

- No merge, no manual production trigger.
- The change touches **both** services:
  - **`helpdesk-api`** (backend): the response shape and query logic changed.
  - **`helpdesk-web`** (frontend): the consumer changed to read the envelope.
  They **must deploy together**; the frontend expects the envelope, so shipping
  only one side would break the ticket list.
- Railway configuration (verified previously): both services deploy from `main`
  automatically with **Wait for CI** (`checkSuites=true`); a single merged
  commit releases both. No database migration is required — the only schema
  change is the response shape, computed from existing tables.
- Post-deployment checklist:
  1. API `/health/ready` → 200; web `/healthz` → `ok`.
  2. `GET /api/v1/tickets?page=1&page_size=20` returns
     `{items,total,page,page_size,total_pages,has_next,has_previous}`.
  3. Walk every page in `/tickets` as an admin: no empty intermediate page, the
     last page may be partial, Next on the last page returns to page 1.
  4. Previous on page 1 goes to the last page.
  5. Change a filter/page size: the list returns to page 1 and the totals match.
  6. `/queue` unassigned tab totals are exact (server-side filter).
- No Neon data was read destructively, modified, or re-seeded during this task.

---

## Unavoidable consistency limitation

Offset pagination is **snapshot**-consistent, not real-time: a ticket inserted or
deleted between two page requests can shift rows across a page boundary, so a
row may appear on two consecutive pages (if something is inserted above it) or be
skipped (if something is deleted above it) while browsing. This is inherent to
`LIMIT/OFFSET`; it is not the reported bug (which was deterministic ordering).
The UI now reconciles an out-of-range current page against the freshly reported
`total_pages`, and always trusts the server's `total`/`has_next`, so browsing
remains correct page-to-page. Removing the limitation entirely would require
cursor pagination, which is out of scope here and unnecessary for the
page-number UI.
