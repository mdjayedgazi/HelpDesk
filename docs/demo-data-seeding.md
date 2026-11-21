# HelpDesk — Demo Data Seeding

**Command:** `python -m app.commands.seed_demo_data`
**Module:** `backend/app/commands/seed_demo_data.py`
**Branch:** `feat/demo-dataset-seeding`
**Companion audit:** [`demo-data-audit.md`](./demo-data-audit.md)
**Seed report:** [`demo-data-seed-report.md`](./demo-data-seed-report.md)

This is the operator runbook and design record for the demo dataset. It describes
what the data is, how it is produced, how to preview it, and the gates that must
hold before it can be written.

---

## 1. Dataset design

The dataset is described by a `DemoPlan` and built from deterministic `uuid5`
identifiers. Every run is reproducible *relative to its anchor time*, and
re-running never duplicates anything.

### 1.1 Why the anchor is `now`, not a fixed date

The analytics endpoint computes its 14-day window from `datetime.now(UTC)`. The
previous version of the seeder anchored every timestamp to a constant
(`2026-08-15`), which placed **all** tickets outside that window — the *Ticket
volume* trend and its sparkline would have rendered a flat zero line while every
other chart looked correct.

The seeder now anchors to the moment it runs. Determinism is preserved by
deriving every offset from that anchor with a fixed RNG seed
(`RNG_SEED = 20261019`).

### 1.2 Users

| Size | Owner | Admin | Agent | Customer | Total | Inactive |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| 100 | 1 | 8 | 20 | 71 | **100** | 3 customers, 2 agents |
| 50 | 1 | 4 | 10 | 35 | **50** | 3 customers, 1 agent |

- The Owner is the **existing preserved row** and is never created, modified or
  given a `clerk_id` by the seeder.
- **There is only ever one Owner.** The database enforces this with the partial
  unique index `uq_users_single_owner` (`ON users (role) WHERE role = 'OWNER'`).
  The brief asked for 2 owners; that is impossible without a schema change, so
  the extra head-count went to Administrators. This is recorded in the audit and
  the report rather than silently approximated.
- Every synthetic user has `clerk_id = NULL`, `username = demo_<role>_NN`,
  `email = demo_<role>_NN@example.test`. They are **not** independently
  authenticable — see §7.

### 1.3 Tickets

| Size | Total | OPEN | IN_PROGRESS | WAITING | RESOLVED | CLOSED |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 300 | 60 | 60 | 60 | 90 | 30 |
| 50 | 150 | 30 | 30 | 30 | 45 | 15 |

Priorities at size 100: LOW 45, NORMAL 135, HIGH 90, URGENT 30 (scaled at 50).
Counts are apportioned with largest-remainder rounding, so they are exact.

Categories are spread evenly across all seven enum values. Every ticket
references a real customer; assigned tickets reference an **active AGENT** only.

### 1.4 Timeline and realistic scenarios

- Creation times span the last **45 days**; the recent bucket is deliberately
  concentrated in the last 14 days so the trend has real daily variation.
- Statuses are shuffled (fixed seed) across the timeline so aging, "created
  today" and "resolved recently" all occur at once.
- **Aging**: a deliberate minority (~1 in 5) of older active tickets has an
  `updated_at` older than 7 days. The rest were reviewed recently. Measured: 24
  aging tickets at size 100.
- **Unassigned**: ~17% of *active* tickets are unassigned, and many are older
  than 24 h, so both `unassigned_tickets` and `unassigned_over_24h` are non-zero.
- **Causal ordering**: `created_at ≤ updated_at ≤ now`;
  `created_at ≤ assigned_at`; `resolved_at` only for RESOLVED/CLOSED and always
  after creation. Verified by SQL after seeding (0 violations).

### 1.5 Conversations, notes and history

- Each ticket gets a public customer message; assigned tickets add a staff reply;
  resolved/closed tickets add a resolution message placed **before** the
  resolution timestamp.
- Roughly every third ticket gets a **staff-only internal note** authored by an
  AGENT or ADMIN. Customers never author internal notes (asserted in tests).
- Ticket history includes `TICKET_CREATED`, `TICKET_ASSIGNED`, `STATUS_CHANGED`
  and `PRIORITY_CHANGED`, causally ordered.

### 1.6 Notifications

- Every ticket produces a customer receipt; a deterministic subset produces
  assignment, status, reply and feedback notifications.
- Unassigned tickets notify an Administrator (`TICKET_NEEDS_ASSIGNMENT`).
- Private staff↔Owner conversation messages and account-request activity also
  notify the correct recipient.
- Read/unread is a deliberate mix (~73% read / 27% unread at size 100, within the
  requested 70–80% band). Internal-message notification state mirrors each
  recipient row's `read_at`, so the inbox and the bell never disagree.

### 1.7 Other entities

Attachments (real files under `/tmp`, `scan_status = CLEAN`), private staff↔Owner
conversations and messages, account-management requests with comments/events,
ticket feedback, and Owner-composed internal messages are all produced with valid
foreign keys.

---

## 2. Role mapping

| Requested | Implemented |
| --- | --- |
| Owner | 1 (the preserved Owner) — the schema allows no more |
| Admin | 8 at 100 / 4 at 50 |
| Agent | 20 at 100 / 10 at 50 |
| Customer | 71 at 100 / 35 at 50 |

Authorization is unchanged: the backend re-checks the role on every request.
Seed data only *satisfies* those rules; it never bypasses them.

---

## 3. Seed command

```bash
cd backend

# 1. Preview the complete plan (no DB connection, no writes).
uv run python -m app.commands.seed_demo_data --dry-run --size 100

# 2. Insert (requires the confirmation token; idempotent).
HELPDESK_DEMO_SEED_CONFIRM='HD-DEMO-20261019 @ <host>/neondb' \
HELPDESK_DEMO_UPLOAD_DIR=/tmp/helpdesk-demo-uploads \
uv run python -m app.commands.seed_demo_data --size 100

# 3. Re-read what is stored, without inserting.
uv run python -m app.commands.seed_demo_data --verify-only --json
```

Options:

| Flag | Effect |
| --- | --- |
| `--size {50,100}` | Users to target (default 100) |
| `--dry-run` | Print the plan; no DB connection, no writes |
| `--verify-only` | Report current counts; inserts nothing |
| `--json` | Machine-readable output |
| `--confirm TOKEN` | Same as the confirmation env var |

Exit codes: `0` success, `2` refused by a guard, `3` completed with conflicts,
`1` unexpected failure (transaction rolled back).

---

## 4. Dry-run procedure

`--dry-run` builds the pure spec lists and prints:

- the exact user/role split and inactive counts;
- ticket totals and the full status/priority breakdown;
- active, unassigned (count and %), urgent-active;
- created-in-last-14-days, aging-over-7-days, unassigned-over-24h;
- comments (and internal-note count), history, notifications, attachments,
  conversations, account requests, feedback, internal messages.

It skips the target/confirmation guards **because it performs no I/O** — that is
what lets an operator inspect the plan before configuring anything. A test
monkeypatches `async_session` to raise and proves the dry-run never opens one.

---

## 5. Production safety gates

All of these must hold before a single row is written:

1. `HELPDESK_DEMO_SEED_CONFIRM` (or `--confirm`) equals
   `HD-DEMO-20261019 @ <verified-host>/neondb`.
2. `DATABASE_URL` host **and** database name match the verified constants.
3. The environment is not `production`/`prod`, **or** the deliberate
   `HELPDESK_DEMO_ALLOW_PRODUCTION=I-UNDERSTAND-THIS-IS-THE-DEMO-DATABASE`
   override is set (needed for the Railway `college-demo` profile, which declares
   `ENVIRONMENT=production`). The override skips nothing else.
4. The attachment upload directory is under `/tmp`.
5. A single OWNER already exists; its row is hashed before and after and the
   transaction rolls back on any drift.

What the seeder will never do: `DROP`, `TRUNCATE`, `DELETE`, alter the schema,
touch migration history, modify the Owner, or write a `clerk_id`.

---

## 6. Idempotency

Every row uses a deterministic `uuid5` primary key. A second run inserts **zero**
rows and reports each entity as `reused`, verified on real PostgreSQL:

```
first  run: users 99, tickets 300, comments 789, ... notifications 525
second run: users 0,  tickets 0,   comments 0,   ... notifications 0
```

If a row exists with the same username/email but a **different** id (a real
collision), the seeder records a conflict and refuses rather than overwriting.

---

## 7. Authentication limitations

Synthetic users have no Clerk identity. They cannot sign in, and the seeder never
fabricates a Clerk id, JWT, session, password or invitation token. To give a
synthetic user real login, a separate authorised Clerk provisioning process is
required — that is out of scope and must not be faked.

The **real Owner remains fully functional** because the seeder never touches the
Owner row. If the Owner were ever missing, recovery is the documented
`python -m app.commands.bootstrap_owner` flow (verified primary email against the
Clerk Backend API), never a hand-written `clerk_id`.

---

## 8. Verification queries

After seeding, these direct SQL checks must all return the expected results:

```sql
-- Exactly one owner, and it has a real Clerk link (not NULL).
SELECT count(*) FROM users WHERE role = 'OWNER';                  -- 1

-- Role split.
SELECT role, count(*) FROM users GROUP BY role ORDER BY role;

-- Status / priority distribution.
SELECT status, count(*) FROM tickets GROUP BY status ORDER BY status;
SELECT priority, count(*) FROM tickets GROUP BY priority ORDER BY priority;

-- No active work assigned to an inactive agent.
SELECT count(*) FROM tickets t JOIN users u ON u.id = t.assignee_user_id
WHERE u.is_active = false
  AND t.status IN ('OPEN','IN_PROGRESS','WAITING_ON_CUSTOMER');      -- 0

-- No impossible timelines.
SELECT count(*) FROM tickets
WHERE resolved_at IS NOT NULL AND resolved_at < created_at;         -- 0

-- No customer-authored internal notes.
SELECT count(*) FROM comments c JOIN users u ON u.id = c.author_user_id
WHERE c.is_internal = true AND u.role = 'CUSTOMER';                 -- 0

-- At least one notification per role, and both read states.
SELECT u.role, n.is_read, count(*) FROM notifications n
JOIN users u ON u.id = n.recipient_user_id GROUP BY u.role, n.is_read;
```

The automated equivalents live in `tests/test_demo_seed_postgres.py` (opt-in,
disposable PostgreSQL) and `tests/test_demo_seed_plan.py` (always runs).

---

## 9. Final insertion counts (verified on disposable PostgreSQL 16)

Size 100, single run:

| Entity | Inserted |
| --- | ---: |
| users (synthetic) | 99 (+1 preserved Owner = 100) |
| tickets | 300 |
| comments | 789 (100 internal) |
| ticket history | 974 |
| notifications | 525 |
| attachments | 12 |
| staff conversations | 12 |
| staff messages | 36 |
| account requests | 12 |
| account-request comments | 21 |
| account-request events | 21 |
| feedback | 34 |
| internal messages | 6 |

Size 50, single run: 49 synthetic + Owner = 50 users, 150 tickets,
394 comments, 301 notifications, 487 history events.

Re-running either size inserts **0** rows.

---

## 10. Verification performed for this change

- `alembic upgrade head` on a fresh disposable database, then the real seeder.
- The real `get_analytics()` endpoint, with every aggregate compared to direct
  SQL — all matched (see the seed report).
- `485` backend tests pass (`pytest -q`), including `31` PostgreSQL seed
  integration tests and `25` new plan/CLI tests.
- `ruff check` and `ruff format --check` clean.
- Production guard exercised: a real run without the confirmation token exits 2;
  a `--dry-run` exits 0 and writes nothing.

**No production write was performed by this pass.** Production execution is
gated on the operator manually clearing records, verifying a Neon recovery
branch, and explicitly approving the exact command (Phase 12 of the brief).
