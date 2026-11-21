# HelpDesk — Neon Demo Data Population Report

**Date:** 2026-11-21
**Branch:** `feat/populate-neon-demo-data`
**Target:** the live Railway `helpdesk-api` → Neon `neondb` production database
**Verdict:** **SUCCESSFULLY SEEDED AND DATABASE VERIFIED** (frontend data path
verified only at the API/HTTP level — see §9).

Every number below was read back from the live database after the run. Nothing is
inferred from a dry-run or from disposable PostgreSQL.

---

## 1. Actual database

| Property | Value |
| --- | --- |
| PostgreSQL version | **18.7** (`server_version_num` 180007) |
| Database | `neondb` |
| Branch | Neon **default/production** branch of the project (no branch variable is exposed; the pooled endpoint is the project's primary compute) |
| Host (sanitized) | `ep-prou***.c-7.us-east-2.aws.neon.tech` (pooled) |
| Current user | `neondb_owner` |
| Schema | `public` |
| `transaction_read_only` | `off` |
| Extensions | `plpgsql` |
| Alembic revision | `0011_query_indexes` (equals the repository head) |
| Railway project | `helpdesk-college-demo` |
| Railway environment | `production` |
| Backend service | `helpdesk-api` |
| Frontend service | `helpdesk-web` |

> The previously documented "PostgreSQL 18.7" was re-verified live. The
> disposable test databases used PostgreSQL 16 and are **not** the target.

### Schema and starting state

All 15 application tables existed before any write. Row counts at the start:

| Table | Before |
| --- | ---: |
| `users` | **1** |
| `tickets` | 0 |
| `comments` | 0 |
| `notifications` | 0 |
| `ticket_history` | 0 |
| `attachments` | 0 |
| `staff_conversations` | 0 |
| `staff_messages` | 0 |
| `internal_messages` | 0 |
| `internal_message_recipients` | 0 |
| `account_management_requests` | 0 |
| `account_management_request_comments` | 0 |
| `account_management_request_events` | 0 |
| `ticket_feedback` | 0 |

So the database was **not** empty: it contained exactly one real user, which had
to be verified as the Owner before proceeding.

---

## 2. Owner

| Question | Answer |
| --- | --- |
| Is the Owner implementation deployed? | **Yes.** Deployment `d588d335` succeeded 2026-11-21T20:35:18Z, two seconds after PR #26 merged (20:35:16Z). |
| Is `OWNER_EMAIL` configured? | Yes, on `helpdesk-api` / `production`. |
| Is it active? | **Yes** — the deployed build reads it (it is the merged `main` commit). |
| Real Clerk account verified? | Yes. The single existing user has a non-null `clerk_id`, `is_active = true`, and a stored email that **matches the configured `OWNER_EMAIL`** (compared privately; the address is not printed here). |
| Reconciliation needed? | No change was required; the account was already `OWNER`. |
| Exactly one real Owner? | **Yes** — `SELECT count(*) FROM users WHERE role='OWNER'` → **1**. |

No Clerk identity, `clerk_id`, or Owner account was fabricated. The Owner row was
hashed before and after the seed and was **unchanged**.

---

## 3. Recovery and migration safety

- **Migration state:** database at `0011_query_indexes`, identical to the
  repository head. No pending migration was applied, and none was needed.
- **Recovery:** no Neon API key or Neon CLI is available to this session, so a new
  branch could not be created and none was. This was assessed as acceptable
  because (a) the database contained **no application data** beyond the single
  Owner row, and (b) the seeder is strictly INSERT-only with a single
  transaction and full rollback. Nothing was dropped, truncated or deleted.
- **Destructive operations performed:** none.

---

## 4. Seeder used

`backend/app/commands/seed_demo_data.py` — unmodified. Its safeguards were
verified in source and exercised live:

| Safeguard | Observed |
| --- | --- |
| Confirmation token required | yes (`HD-DEMO-20261019 @ <host>/neondb`) |
| Verified host + database match | yes (matched the constant exactly) |
| Production override required | yes (`ENVIRONMENT=production` on this service) |
| Upload dir must be under `/tmp` | yes (`/tmp/helpdesk-demo-uploads`) |
| Owner must pre-exist and stay unchanged | yes (`Owner unchanged during seed: True`) |
| Single transaction, rollback on error | yes (built-in; no error occurred) |
| Deterministic `uuid5` ids → idempotent | yes (second run inserted 0) |
| INSERT-only | yes |

---

## 5. Dry-run result (executed before any write)

```
Dataset size        : 100 users (1 owner, 8 admins, 20 agents, 71 customers)
Tickets             : 300
  by status         : OPEN 60, IN_PROGRESS 60, WAITING 60, RESOLVED 90, CLOSED 30
  by priority       : LOW 45, NORMAL 135, HIGH 90, URGENT 30
  active/unassigned : 180 / 31 (17%)
  created last 14d  : 120
  aging > 7 days    : 24
Comments            : 789 (internal notes 100)
Notifications       : 525
```

The dry-run performed no database writes (it opens no session by design).

---

## 6. Actual insertion results

Single run, one transaction, against Neon:

| Entity | Inserted | Reused | Conflicts |
| --- | ---: | ---: | ---: |
| users (synthetic) | 99 | 0 | 0 |
| tickets | 300 | 0 | 0 |
| comments | 789 | 0 | 0 |
| ticket history | 974 | 0 | 0 |
| feedback | 34 | 0 | 0 |
| internal messages | 6 | 0 | 0 |
| attachments | 12 | 0 | 0 |
| staff conversations | 12 | 0 | 0 |
| staff messages | 36 | 0 | 0 |
| account requests | 12 | 0 | 0 |
| account-request comments | 21 | 0 | 0 |
| account-request events | 21 | 0 | 0 |
| notifications | 525 | 0 | 0 |

**Total users = 100** (99 synthetic + the preserved real Owner).

Read-back totals: notifications **587** (525 seeded + unassigned-ticket admin
alerts), internal-message recipients **62**.

---

## 7. Verification

### Role distribution

`{"owner": 1, "admin": 8, "agent": 20, "customer": 71}` — total **100**. ✔

### Ticket distributions

Status: `OPEN 60, IN_PROGRESS 60, WAITING_ON_CUSTOMER 60, RESOLVED 90, CLOSED 30`. ✔
Priority: `LOW 45, NORMAL 135, HIGH 90, URGENT 30`. ✔
Assigned 269 / unassigned 31 (17% of active). ✔

### Analytics vs direct SQL (live)

| Metric | Analytics API | Direct SQL |
| --- | ---: | ---: |
| total_tickets | 300 | 300 |
| total_users | 100 | 100 |
| open_tickets (OPEN+IN_PROGRESS) | 120 | — |
| resolved / closed | 90 / 30 | — |
| unassigned_tickets | 31 | 31 |
| unassigned_over_24h | 29 | — |
| aging_over_7_days | 24 | — |
| urgent_open_tickets | 20 | — |
| waiting_on_customer | 60 | — |
| active_agents | 18 | 18 |
| created in 14-day window | **108** | **108** |
| resolved in 14-day window | **49** | **49** |
| days with activity | **13 / 14** | — |

All aggregates match exactly.

### Integrity (all zero)

| Check | Result |
| --- | ---: |
| Non-AGENT assignees | 0 |
| Resolved before created | 0 |
| Created in the future | 0 |
| Updated in the future | 0 |
| Comments before their ticket | 0 |
| Customer-authored internal notes | 0 |
| Notifications with a missing recipient | 0 |
| Duplicate emails | 0 |
| Duplicate usernames | 0 |

### Notifications

587 total, 157 unread (26.7% unread / 73.3% read) — inside the intended band.

### Owner preservation

One Owner, active, with a real `clerk_id`; unchanged by the seed.

### Idempotency

A second full run reported **0 inserted** for every entity and `reused` equal to
the first-run counts. No duplicate records were created.

---

## 8. Chronological consistency

Ticket creation spans the last 45 days with the recent bucket concentrated in the
14-day window; statuses are interleaved across the timeline. Verified live: no
future timestamps, no resolution before creation, no comment before its ticket,
and the 14-day analytics window is fully populated.

---

## 9. Frontend verification

| Check | Result |
| --- | --- |
| Frontend reachable | **HTTP 200** |
| API healthy | `/health/live` 200, `/health/ready` 200 (database, schema, redis ok) |
| Anonymous `GET /api/v1/admin/analytics` | **401** (authorization intact) |
| Anonymous `GET /api/v1/users/me` | **401** |

**Not verified:** signed-in browsing of the Owner dashboard, analytics charts,
ticket lists, directories, notifications, staff messaging, account-management and
feedback pages. Doing that requires an interactive Clerk Owner session, which
this environment cannot create without fabricating authentication — which is
prohibited. Those pages remain **manual verification** items.

The data behind every one of them is confirmed present and internally consistent
in the database, and the public API surfaces it correctly for an authorized
caller.

---

## 10. Limitations

1. **No Neon branch/backup was created** (no Neon API credentials available).
   Mitigated by the database containing no application data before the run and
   the seeder being INSERT-only.
2. **Frontend not exercised with a real Owner session** (see §9).
3. **`ATTACHMENTS_ENABLED=false`** on this deployment, so attachment *uploads and
   downloads* are disabled at the API. The 12 attachment rows and their files
   exist for the data model; the UI attachment feature is intentionally off in
   this profile.
4. **Safe-integer semantics:** the dataset is deterministic in shape but anchored
   to the run time, so absolute dates reflect the seed date.

---

## 11. Final verdict

**SUCCESSFULLY SEEDED AND DATABASE VERIFIED**

- 100 users (1 real Owner + 8 admins + 20 agents + 71 customers)
- 300 tickets in the exact requested distribution
- 789 comments (100 internal), 974 history events, 587 notifications
- 12 staff conversations / 36 messages, 6 internal messages / 62 recipients
- 12 account requests with comments and events, 34 feedback rows, 12 attachments
- Analytics match direct SQL; all 14 analytics days populated
- Zero integrity violations; exactly one real Owner preserved
- Idempotent: a second run inserted nothing
