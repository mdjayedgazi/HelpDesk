# HelpDesk — Demo Dataset: Database & Backend Audit

**Audit date:** 2026-11-21
**Repository:** `mdjayedgazi/HelpDesk`
**Branch:** `feat/demo-dataset-seeding` (new, from `main` @ `69045ff`)
**Purpose:** Establish exactly what the production database and analytics layer
support *before* writing a single demo row.

This audit was produced by reading the real models, migrations, routers, services
and tests. Nothing here is assumed from a feature description. Where a capability
is absent it is stated as absent.

---

## 1. Git and deployment state

| Item | Finding |
| --- | --- |
| `main` HEAD | `69045ff` — merge of PR #24 |
| PR #22 | **MERGED** (`4ea4a2e`) |
| PR #23 | **MERGED** (`8e6868d`) |
| PR #24 | **MERGED** (`69045ff`) — motion QA follow-up |
| Open PRs | none |
| Working tree | `data.md` was emptied locally; restored during this pass and replaced with this review at the end |
| New branch | `feat/demo-dataset-seeding` |

No existing PR was modified. No deployment was triggered.

---

## 2. Existing seeding capability (important)

The repository **already contains two seeders**. This is the single most
important finding of the audit, because it changes the job from "write a seeder"
to "make the existing, reviewed seeder fit the requirement".

| Module | Target | Guard |
| --- | --- | --- |
| `app/commands/seed_demo_data.py` (2,179 lines) | Neon **development** database | refuses loopback, refuses QA-named DBs, requires an exact confirm token that names the host+db, refuses `ENVIRONMENT=production`, refuses upload dirs outside `/tmp`, hashes the Owner row before/after and rolls back on drift |
| `app/commands/seed_qa_data.py` (~1,000 lines) | **loopback-only** isolated QA DB | refuses non-loopback hosts, requires `HELPDESK_QA_SEED=1` |

Both are idempotent: every row uses a deterministic `uuid5` primary key, so a
re-run inserts nothing and duplicates nothing. Both are non-destructive:
INSERT-only, no `TRUNCATE`, no `DELETE`, no schema change. Both are opt-in
commands that nothing imports at startup.

### 2.1 What `seed_demo_data` already produces

- 99 synthetic users + the preserved Owner = **100 users**
  (5 ADMIN, 15 AGENT, 79 CUSTOMER)
- 120 tickets covering every status, priority and category
- public comments + staff-only internal notes
- ticket history events (`TICKET_CREATED`, `TICKET_ASSIGNED`, `STATUS_CHANGED`,
  `PRIORITY_CHANGED`)
- notifications for all four roles, including read/unread mixes
- ticket attachments with real files written under `/tmp`
- private staff↔Owner conversations and messages
- account-management requests, comments and events
- ticket feedback, and Owner-composed internal messages

This is a genuinely strong dataset and it already satisfies most of the request.

### 2.2 Critical defect found — timestamps are frozen in the past

`_BASE = datetime(2026, 8, 15, 7, 0, tzinfo=UTC)` and every timestamp is
`_BASE + timedelta(...)`. The whole dataset therefore sits in **August 2026**.

The analytics endpoint (`app/api/routers/analytics.py`) computes its 14-day
window from `datetime.now(UTC)`:

```python
now = datetime.now(UTC)
since = now - timedelta(days=window_days - 1)   # 14 days
```

Verified consequence:

```
seeded ticket range: 2026-08-15 07:30 UTC → 2026-08-18 08:53 UTC
now:                 2026-11-21 18:04 UTC
analytics window:    2026-11-08 → 2026-11-21
=> every seeded ticket is outside the window
```

So after seeding, the two charts that depend on recent activity — the *Ticket
volume* trend and its sparkline — would render **all zeros**, while every
status/priority/category aggregate would be correct. That is a real, visible
defect and the primary reason this pass is needed.

It also breaks the requested aging scenarios: the analytics definition of
"aging" is `updated_at <= now - 7 days`, which the August rows satisfy, but
"some tickets created today / yesterday" and "a meaningful distribution across
the previous 14 days" are impossible with a frozen base.

**Fix:** anchor generated timestamps to the time of seeding (`now`), not a
constant. This is a small, contained change that preserves determinism *relative
to the run* while making the dataset land inside the dashboard window.

### 2.3 Requirement mismatches to close

| Request | Existing seeder | Action |
| --- | --- | --- |
| `--size 50` and `--size 100` | fixed at 100 | add `--size` |
| `--dry-run` | absent (`--verify-only` reads existing rows) | add `--dry-run` |
| `python -m app.seed_demo` | `python -m app.commands.seed_demo_data` | keep the module path (documented CLI conventions) and document it |
| 2 owners in the 100 dataset | exactly 1 owner, enforced by a **partial unique index** | **cannot comply** — see §3.1 |
| ~300 tickets for 100 users | 120 | make ticket count size-dependent |
| 14-day trend populated | frozen in August | anchor to `now` |
| ~600–900 comments | ~200+ public + internal | scale with size |
| ~300–500 notifications | ~200+ | scale with size |
| Deterministic | deterministic uuid5 | preserved |

---

## 3. Database inventory (verified)

Ten tables. All primary keys are `uuid.UUID`. All timestamps are
`DateTime(timezone=True)`.

### 3.1 `users`

| Column | Type | Constraints |
| --- | --- | --- |
| `id` | uuid | PK |
| `clerk_id` | varchar(255) | unique, nullable — **the Clerk link** |
| `full_name` | varchar(120) | not null |
| `username` | varchar(90) | unique, indexed |
| `email` | varchar(255) | unique, indexed, `CHECK email = lower(email)` |
| `image_url` | varchar(512) | nullable |
| `password_hash` | varchar(255) | nullable (Clerk owns passwords) |
| `role` | enum `Role` | default `CUSTOMER` |
| `is_active` | bool | default true |
| `created_at`, `updated_at` | timestamptz | server defaults |

**Partial unique index `uq_users_single_owner`** (`ON users (role) WHERE role =
'OWNER'`, migration `0003_single_owner_index.py`) — *the database itself permits
at most one Owner.*

> **Blocking finding.** The request asks for **2 owners** in the 100-user
> dataset. The schema forbids it, and the application's whole ownership model
> depends on the invariant (see `app/core/permissions.py`: Owner is the only
> role that may change roles, and `bootstrap_owner` refuses to run once an Owner
> exists). Creating a second Owner would require a schema change and would break
> `uq_users_single_owner`; the seeder's own guard would also refuse.
> **Decision: honour the schema. One Owner, never two.** The requested 100-user
> split is therefore realised as 1 Owner + 8 Admin + 20 Agent + 71 Customer = 100,
> and the 50-user split as 1 Owner + 4 Admin + 10 Agent + 35 Customer = 50.
> This is documented in the report rather than silently approximated.

### 3.2 `tickets`

Columns: `id`, `ticket_number` (unique, indexed, starts at 10000), optional
`client_request_id` (partial unique with the creator), `title` (180),
`description` (Text), `status`, `priority`, `category`, optional `contact_phone`,
`created_by_user_id` → users, `assignee_user_id` → users (nullable),
`assigned_at`, `created_at`, `updated_at`, `resolved_at`.

Indexes: `created_by_user_id`, `assignee_user_id`, `created_at`,
`uq_tickets_creator_request_key` (partial).

No DB-level rule forces the assignee to be an AGENT — that is enforced by the
application service. The seeder must respect it anyway (it does, and the test
suite asserts `assignee_roles <= {AGENT}`).

### 3.3 `comments`

`id`, `ticket_id` → tickets (indexed), `author_user_id` → users, `body` (Text),
**`is_internal`** (bool, default false), `created_at`, `updated_at` (nullable).

`is_internal` is the visibility switch. The API only returns internal comments to
staff; the seeder only lets AGENT/ADMIN author them (test-asserted).

### 3.4 `notifications`

`id`, `recipient_user_id` → users (indexed), `related_ticket_id` → tickets,
`related_conversation_id` → staff_conversations, `related_internal_message_id` →
internal_messages, `related_account_request_id` → account_management_requests,
`type` (enum), `title` (180), `message` (500), `is_read`, `created_at`.

Composite index `(recipient_user_id, created_at)` serves the panel.

### 3.5 `ticket_history`

`id`, `ticket_id`, `actor_user_id`, `event_type` (varchar 40), `old_value` (JSON),
`new_value` (JSON), `created_at`. Event types used by the app and seeder:
`TICKET_CREATED`, `TICKET_ASSIGNED`, `STATUS_CHANGED`, `PRIORITY_CHANGED`.

### 3.6 `attachments`

`id`, `ticket_id`, `uploaded_by_user_id`, `original_filename`, `storage_key`,
`content_type`, `size_bytes`, `scan_status` (`PENDING`/`CLEAN`/`INFECTED`),
`created_at`. Only `CLEAN` may be downloaded; the demo seeder writes real small
files under `/tmp` and marks them `CLEAN`.

### 3.7 Other tables

- `staff_conversations` — unique `staff_user_id` (one thread per staff member),
  `owner_user_id`, `subject`, timestamps.
- `staff_messages` — `conversation_id`, `sender_user_id`, `body`, `read_at`.
- `internal_messages` + `internal_message_recipients` — Owner broadcasts with
  per-recipient `read_at` snapshots.
- `account_management_requests`, `account_management_request_comments`,
  `account_management_request_events`.
- `ticket_feedback` — unique `ticket_id`, rating 1–5 check constraint.

---

## 4. Enumerations (exhaustive)

| Enum | Values |
| --- | --- |
| `Role` | `CUSTOMER`, `AGENT`, `ADMIN`, `OWNER` |
| `TicketStatus` | `OPEN`, `IN_PROGRESS`, `WAITING_ON_CUSTOMER`, `RESOLVED`, `CLOSED` |
| `TicketPriority` | `LOW`, `NORMAL`, `HIGH`, `URGENT` |
| `TicketCategory` | `BILLING`, `ACCOUNT_ACCESS`, `TECHNICAL`, `OUTAGE`, `BUG`, `ACCOUNT_MANAGEMENT`, `OTHER` |
| `EscalationStatus` | `PENDING`, `IN_REVIEW`, `APPROVED`, `REJECTED`, `COMPLETED` |
| `EscalationCategory` | `ACCOUNT_RECOVERY`, `IDENTITY_LINKING`, `PROFILE_CORRECTION`, `ROLE_OR_STATUS_CHANGE`, `OTHER` |
| `AttachmentScanStatus` | `PENDING`, `CLEAN`, `INFECTED` |
| `InternalAudience` | `everyone`, `agents`, `admins`, `individual` |
| `NotificationType` | `TICKET_ASSIGNED`, `NEW_COMMENT`, `STATUS_CHANGED`, `PRIORITY_CHANGED`, `TICKET_NEEDS_ASSIGNMENT`, `STAFF_MESSAGE_RECEIVED`, `OWNER_MESSAGE_RECEIVED`, `ESCALATION_CREATED`, `ESCALATION_UPDATED`, `TICKET_CREATED`, `TICKET_RESOLVED`, `INTERNAL_MESSAGE_RECEIVED` |

No new enum value was introduced.

---

## 5. Authorization model (backend is the source of truth)

| Role | Capabilities |
| --- | --- |
| `CUSTOMER` | own tickets only; public comments; own feedback; own notifications; own profile |
| `AGENT` | assigned tickets + unassigned queue; public + **internal** comments; private staff↔Owner messaging; account-request creation |
| `ADMIN` | all tickets, assignment, user directory (read), account-request review, analytics + dashboard |
| `OWNER` | everything an admin can do **plus** role/activation changes via `can_manage_users`, and the only author/recipient authority for Owner broadcasts |

Dependencies read the local `role` column on every request; Clerk proves identity
only. The seeder never invents a Clerk identity: synthetic users have
`clerk_id = NULL`, which is exactly how `bootstrap_owner` and signup expect
unlinked rows to look.

### 5.1 The real Owner account

- The Owner is identified by `role = 'OWNER'`, and there can be only one.
- `clerk_id` is the Clerk link; the seeder **never** writes it for the Owner and
  never modifies any Owner column.
- `seed()` hashes the Owner row (`id`, `clerk_id`, `full_name`, `username`,
  `email`, `role`, `is_active`, timestamps) before and after the transaction and
  raises `SeedRefused` + rolls back if anything changed.
- If no Owner exists, `seed()` refuses to run rather than inventing one.
- Recovery, if the Owner were ever missing, is the documented
  `python -m app.commands.bootstrap_owner` flow (verified primary email against
  the Clerk Backend API) — never a hand-written `clerk_id`.

---

## 6. Analytics compatibility

`GET /api/v1/admin/analytics` (admin/owner only) returns:

| Field | Definition | Demo data must satisfy |
| --- | --- | --- |
| `totals.total_tickets` | count of tickets | matches ticket count |
| `totals.open_tickets` | OPEN + IN_PROGRESS | derived, no special action |
| `totals.unassigned_tickets` | active AND `assignee_user_id IS NULL` | needs unassigned **active** tickets |
| `totals.resolved_tickets` / `closed_tickets` | by status | derived |
| `totals.urgent_open_tickets` | URGENT AND status in (OPEN, IN_PROGRESS) | needs urgent tickets that are *not* resolved |
| `totals.total_users` / `active_agents` / `active_admins` | user counts | derived from the 100/50 users |
| `tickets_by_status` / `_priority` / `_category` | grouped counts | need distribution |
| `daily[]` (14 points) | created/resolved grouped by **day within the last 14 days** | **the frozen-August defect breaks this** |
| `aging_over_7_days` | active AND `updated_at <= now - 7d` | needs old active tickets |
| `unassigned_over_24h` | unassigned active AND `created_at <= now - 24h` | needs old unassigned tickets |
| `waiting_on_customer` | status count | derived |
| `agent_workload[]` | per **active AGENT**: active, urgent, resolved counts | needs realistic spread |

`GET /api/v1/admin/dashboard` is a simpler legacy aggregate with
`total_tickets`, `tickets_by_status`, `tickets_by_priority`, `total_users`,
`active_agents`.

Two more derived values the UI computes client-side from the same payload
(`frontend/src/lib/analytics.ts`): `resolutionShare` = resolved / (resolved +
closed), `assignmentCoverage` = (open + waiting − unassigned) / (open + waiting),
and half-window deltas from `daily`. None needs extra data, but all need the
14-day window to be populated.

**Metrics that cannot be produced and must not be faked:** SLA compliance (no
target column), first-response time (no first-response timestamp), real-time
updates (no websocket/polling), "delivered" notification state (only read/unread).

---

## 7. Data generation constraints (binding rules for the seeder)

1. **INSERT only.** No `DROP`, `TRUNCATE`, `DELETE`, schema or migration change.
2. **Exactly one Owner**, preserved untouched, never assigned a fabricated
   `clerk_id`.
3. **Assignees must be AGENTs**; never assign active work to an inactive agent.
4. **Internal notes only by AGENT/ADMIN.**
5. **Notification recipients must own the referenced row** (ticket, conversation
   participant, internal-message recipient, account request).
6. **Timestamps must be causally ordered**: `created_at ≤ assigned_at ≤
   resolved_at`; no comment before its ticket; no resolution before creation; no
   future timestamps.
7. **Timestamps anchored to `now`** so the 14-day analytics window is populated.
8. **Deterministic ids** (`uuid5`) so re-runs are idempotent.
9. **Reserved identities only**: `@example.test` emails, `demo_*` usernames,
   `clerk_id = NULL`.
10. **No tokens, JWTs, passwords, invitations or secrets** of any kind.
11. **Attachments only when a real file can be written** to a safe directory
    (`/tmp` for the demo command).
12. **Atomic**: one transaction; roll back everything on any failure, and remove
    files written during the failed attempt.

---

## 8. Unsupported / deliberately absent

| Requested | Reality |
| --- | --- |
| 2 Owners | **Blocked** by `uq_users_single_owner` and the ownership model |
| Independent login for synthetic users | **Not possible**: they have no Clerk identity. Enabling that would require a separate authorised Clerk user-provisioning process, which is out of scope and must not be faked |
| SLA metrics | No columns exist; not generated |
| Real email/SMS/webhooks | Not triggered; records are inserted directly |
| `python -m app.seed_demo` | The repository convention is `app.commands.*`; the documented command is `python -m app.commands.seed_demo_data` |
| A second animation/seed dependency | None added |

---

## 9. Planned changes (from this audit)

1. Anchor all demo timestamps to `datetime.now(UTC)` so the 14-day trend,
   aging, and "created today/yesterday" scenarios are real.
2. Add `--size {50,100}` with the schema-legal role split and
   size-proportional ticket/comment/notification counts.
3. Add `--dry-run`, which computes and prints the full plan without opening a
   write transaction.
4. Keep every existing guard (confirm token, host match, `/tmp` uploads,
   production refusal, Owner hash, idempotent re-run, atomic rollback).
5. Scale the dataset to the requested targets where the schema allows:
   ~300 tickets for 100 users / ~150 for 50, ~600–900 comments, ~300–500
   notifications, 15–20% unassigned **active** tickets, urgent tickets spread
   across statuses.
6. Add regression tests for the new behaviours (window coverage, size scaling,
   dry-run writes nothing, causal timestamps).
7. Validate end-to-end on a **disposable local PostgreSQL 16** (available in
   this environment), including running the real analytics endpoint and
   comparing every aggregate against direct SQL.

Production execution itself is gated on explicit operator approval and a manual
cleanup performed by the operator; this pass does not write to Neon.
