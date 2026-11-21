# HelpDesk — Demo Data Seed Report

**Date:** 2026-11-21
**Branch:** `feat/demo-dataset-seeding`
**Module:** `backend/app/commands/seed_demo_data.py`
**Validation target:** disposable local **PostgreSQL 16.15** (Docker), migrated
with `alembic upgrade head`
**Production write:** **not performed** — see §11.

Everything in this report was measured. Nothing is estimated. Where something
could not be verified it is marked as such.

---

## 1. Database tables populated

| Table | Populated |
| --- | --- |
| `users` | yes (1 Owner + synthetic staff/customers) |
| `tickets` | yes |
| `comments` | yes (public + internal) |
| `ticket_history` | yes |
| `notifications` | yes |
| `attachments` | yes (real files, `scan_status=CLEAN`) |
| `staff_conversations` | yes |
| `staff_messages` | yes |
| `internal_messages` | yes |
| `internal_message_recipients` | yes |
| `account_management_requests` | yes |
| `account_management_request_comments` | yes |
| `account_management_request_events` | yes |
| `ticket_feedback` | yes |

No table was created, altered or dropped. No migration was modified.

---

## 2. Actual inserted record counts (size 100)

First run on a freshly migrated, otherwise-empty database:

| Entity | Inserted | Reused | Conflicts |
| --- | ---: | ---: | ---: |
| users | 99 | 0 | 0 |
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

**Second run:** every entity inserted `0` and reused its full first-run count. The
Owner row hash was identical before and after both runs (`owner_unchanged: true`).

Size 50 first run: 49 synthetic users (+1 Owner = 50), 150 tickets, 394 comments,
487 history events, 301 notifications.

---

## 3. Record counts by role (size 100)

| Role | Count |
| --- | ---: |
| owner | 1 |
| admin | 8 |
| agent | 20 |
| customer | 71 |
| **total** | **100** |

Inactive accounts: 3 customers + 2 agents. The Owner is always active.

> The brief asked for 2 owners. The schema's partial unique index
> `uq_users_single_owner` permits exactly one, and the ownership model depends on
> that invariant. The extra head-count went to Administrators. This is a
> deliberate, documented deviation, not an approximation.

---

## 4. Ticket status distribution (size 100)

| Status | Count | Target |
| --- | ---: | ---: |
| OPEN | 60 | 60 |
| IN_PROGRESS | 60 | 60 |
| WAITING_ON_CUSTOMER | 60 | 60 |
| RESOLVED | 90 | 90 |
| CLOSED | 30 | 30 |
| **total** | **300** | **300** |

Size 50: 30/30/30/45/15 = 150.

---

## 5. Priority distribution (size 100)

| Priority | Count | Target |
| --- | ---: | ---: |
| LOW | 45 | 45 |
| NORMAL | 135 | 135 |
| HIGH | 90 | 90 |
| URGENT | 30 | 30 |
| **total** | **300** | **300** |

Urgent tickets are spread across statuses (not all resolved): 20 are still
OPEN/IN_PROGRESS, which is why `urgent_open_tickets` reports 20.

---

## 6. Category distribution (size 100)

| Category | Count |
| --- | ---: |
| BILLING | 43 |
| ACCOUNT_ACCESS | 43 |
| TECHNICAL | 42 |
| OUTAGE | 43 |
| BUG | 43 |
| ACCOUNT_MANAGEMENT | 43 |
| OTHER | 43 |

Every supported category is represented; no new category was invented.

---

## 7. Comments and internal notes (size 100)

| Metric | Value |
| --- | ---: |
| Total comments | 789 |
| Internal notes | 100 |
| Public comments | 689 |
| Internal notes authored by a CUSTOMER | **0** |

Internal notes are authored only by AGENT/ADMIN (SQL-verified: 0 customer-authored
internal notes). Sample bodies are realistic ("linked to the outage incident",
"awaiting confirmation from the billing vendor", etc.).

---

## 8. Notifications (size 100)

| Metric | Value |
| --- | ---: |
| Total | 525 (587 including unassigned-ticket admin alerts in the earlier run) |
| Read | ~73% |
| Unread | ~27% |

Measured on the final validation run: 587 rows, 157 unread (26.7% unread,
73.3% read) — inside the requested 70–80% / 20–30% band.

Notification types represented (SQL-verified in the integration suite):
`TICKET_CREATED`, `TICKET_ASSIGNED`, `NEW_COMMENT`, `STATUS_CHANGED`,
`TICKET_NEEDS_ASSIGNMENT`, `TICKET_RESOLVED`, `INTERNAL_MESSAGE_RECEIVED`,
`OWNER_MESSAGE_RECEIVED`, `STAFF_MESSAGE_RECEIVED`, `ESCALATION_CREATED`,
`ESCALATION_UPDATED`.

Every notification's recipient owns the referenced row; internal-message
notification read state matches the recipient row's `read_at` exactly.

---

## 9. Agent workload (size 100)

The analytics endpoint reported **18 active agents** with assigned work, ordered
by live load:

| Agent | Active | Urgent | Resolved |
| --- | ---: | ---: | ---: |
| Kai Marchetti | 12 | 3 | 3 |
| Clara Kowalski | 10 | 3 | 5 |
| Diego Lindholm | 10 | 1 | 6 |
| … (15 more) | | | |

Total active assigned work across agents: 149. The spread is deliberately uneven,
which is what makes the workload chart meaningful.

---

## 10. Aging and queue records

| Metric | Value |
| --- | ---: |
| Active tickets | 180 |
| Unassigned active | 31 (**17%** of active) |
| Unassigned over 24h | 29 |
| Aging over 7 days | 24 |
| Urgent active | 20 |

All four "attention" categories are non-zero, so the dashboard's attention strip
and the related metrics have real content to show.

---

## 11. Analytics comparison (endpoint vs direct SQL)

The real `get_analytics()` handler was called against the seeded database and
compared with direct SQL aggregates.

| Field | API | Direct SQL | Match |
| --- | ---: | ---: | :---: |
| total_tickets | 300 | 300 | ✓ |
| total_users | 100 | 100 | ✓ |
| open_tickets (OPEN+IN_PROGRESS) | 120 | 120 | ✓ |
| resolved_tickets | 90 | 90 | ✓ |
| closed_tickets | 30 | 30 | ✓ |
| unassigned_tickets | 31 | 31 | ✓ |
| unassigned_over_24h | 29 | 29 | ✓ |
| aging_over_7_days | 24 | 24 | ✓ |
| urgent_open_tickets | 20 | 20 | ✓ |
| waiting_on_customer | 60 | 60 | ✓ |
| tickets_by_status | exact | exact | ✓ |
| tickets_by_priority | exact | exact | ✓ |
| tickets_by_category | exact | exact | ✓ |
| active_agents | 18 | 18 | ✓ |
| active_admins (ADMIN+OWNER active) | 9 | 9 | ✓ |

### 14-day trend

| Metric | Value |
| --- | ---: |
| `window_days` | 14 |
| Days with at least one creation | 14 / 14 |
| Days with at least one resolution | 14 / 14 |
| Created total in window | 108 |
| Resolved total in window | 49 |

This is the direct proof that the frozen-timestamp defect is fixed: previously
every one of these numbers would have been 0.

---

## 12. Data integrity results

All checks returned clean:

| Check | Result |
| --- | ---: |
| Tickets resolved before creation | 0 |
| Tickets created in the future | 0 |
| Comments before their ticket | 0 |
| Assigned tickets whose assignee is not an AGENT | 0 |
| Internal notes authored by a CUSTOMER | 0 |
| Orphaned foreign keys (tickets, comments, notifications, attachments) | 0 |
| Duplicate demo usernames / emails | 0 |
| Duplicate tickets across two runs | 0 |
| Owner `clerk_id` modified | no |
| Owner row changed (hash before vs after) | no |

---

## 13. Tests executed

| Suite | Result |
| --- | --- |
| Full backend suite (`pytest -q`) | **485 passed**, 58 skipped (PostgreSQL/Redis opt-in) |
| `tests/test_demo_seed_plan.py` (new, always runs) | 25 passed |
| `tests/test_demo_seed_postgres.py` (disposable PG 16) | 31 passed |
| `ruff check .` | clean |
| `ruff format --check .` | 117 files formatted |
| Frontend `tsc --noEmit` | clean |
| Frontend tests | 136 passed |

The 58 skips are the existing opt-in PostgreSQL/Redis integration suites that
need external services; they are unrelated to this change and were separately
exercised for the seed suite against a real disposable database.

---

## 14. Production safety verification

| Gate | Verified |
| --- | --- |
| No confirmation token → exit 2 | yes |
| `--dry-run` → exit 0, no DB connection | yes (test monkeypatches `async_session` to raise) |
| Wrong host / wrong DB name → refused | yes (unit test) |
| Upload dir outside `/tmp` → refused | yes |
| Declared `production` without override → refused | yes |
| Declared `production` with exact override phrase → allowed | yes |
| Any other guard skipped by the override | **no** |
| Seeder emits no `clerk_id`, JWT, password or token | yes |
| Schema / migrations modified | no |
| Data deleted or truncated | no |

**Note on the production environment.** The Railway `helpdesk-api` service
declares `ENVIRONMENT=production` (profile `college-demo`). The original guard
would have refused it, so an explicit, non-default override
(`HELPDESK_DEMO_ALLOW_PRODUCTION=I-UNDERSTAND-THIS-IS-THE-DEMO-DATABASE`) was
added. It is a deliberate act that skips nothing else.

---

## 15. Production verification

**Not performed.** This pass did not write to Neon. Required before a production
run, and outside what could be done here:

1. Operator verifies a recoverable Neon branch/backup exists.
2. Operator manually clears the intended application records (the task explicitly
   reserved this).
3. Operator confirms the preserved Owner row is intact.
4. Operator runs the dry-run and approves the exact command.
5. The command is executed once with the confirmation token (and, on this
   deployment, the production override), via
   `railway run --service helpdesk-api …`.
6. The live dashboards are inspected with the real Owner session.

The live application was **not** inspected with seeded data, because no production
write occurred and no authorised Clerk session was available in this environment.

---

## 16. Remaining limitations

1. **One Owner, not two.** Enforced by `uq_users_single_owner`. Requesting two
   would require a schema change that breaks the ownership model.
2. **Synthetic users cannot sign in.** They carry no Clerk identity by design.
   Enabling that needs a separate authorised Clerk provisioning process and must
   not be faked.
3. **No SLA / first-response metrics.** The columns do not exist, so the seeder
   does not fabricate them.
4. **Attachments are only real files under `/tmp`.** In the production profile
   `ATTACHMENTS_ENABLED=false`, so attachment upload/download is disabled there;
   the rows and small files still exist for the data model and tests.
5. **The demo anchor is the run time.** Two runs at different times produce
   datasets whose *relative* shape is identical but whose absolute dates differ.
   That is intentional (it keeps the 14-day window populated) and is documented.
6. **Live role-by-role browsing was not performed** (no Clerk session). Role
   behaviour is covered by the API authorization test suite instead.
