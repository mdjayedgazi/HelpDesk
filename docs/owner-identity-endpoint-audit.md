# HelpDesk — Owner Identity & Endpoint Audit

**Audit date:** 2026-11-21
**Repository:** `mdjayedgazi/HelpDesk`
**Branch audited:** `main` @ `917af4b` (merge of PR #25)
**Purpose:** Inventory every backend endpoint and the existing Owner mechanism
before implementing configurable Owner identity.

Nothing here is assumed. Every row was read from source.

---

## 1. Repository and remote state

| Item | Finding |
| --- | --- |
| `main` HEAD | `917af4b` — merge of PR #25 (demo seeding) |
| Open PRs | none |
| Merged PRs | #19, #20, #21, #22, #23, #24, #25 |
| Existing feature branches | `feat/demo-dataset-seeding`, `feat/helpdesk-motion-visual-polish`, `feat/helpdesk-ui-ux-modernization` (all merged) |
| `gh auth` | authenticated as `mdjayedgazi` with `repo`, `workflow` scopes |
| Working tree | `data.md` locally emptied again; preserved from `HEAD` and extended at the end of this task |
| Existing owner implementation | `app/commands/bootstrap_owner.py` + `INITIAL_ADMIN_EMAIL` setting |

---

## 2. Existing Owner mechanism (the thing being replaced)

### 2.1 `INITIAL_ADMIN_EMAIL`

- Declared in `app/core/config.py` as `INITIAL_ADMIN_EMAIL: str | None = None`.
- Exposed via the `initial_admin_email` property (trimmed + lowercased, `None`
  when blank).
- Read **only** by `app/commands/bootstrap_owner.py` and `seed_qa_data.py`.
- The docstring is explicit: *"It is never consulted on the request path: the
  application no longer elevates or demotes anyone based on this setting."*
- Present in `backend/.env.example` line 26.
- **Not currently set** in the Railway `helpdesk-api` service.

### 2.2 `bootstrap_owner`

`promote_owner(session, *, clerk, configured_email)`:

1. refuses if `configured_email` is unset;
2. refuses if **any** Owner already exists (cannot transfer);
3. finds the local user by exact email;
4. requires `clerk_id` already linked;
5. requires `is_active`;
6. calls `clerk.users.get_async(user_id=...)` and compares
   `_verified_primary_email(clerk_user)` to the configured email;
7. sets `role = OWNER` and commits.

It never creates a user, never writes a `clerk_id`, and never transfers ownership.

### 2.3 Request-path synchronization (`app/core/auth.py`)

`get_current_user`:

1. resolves the local user by `clerk_id` from the trusted token `sub`;
2. **returns the stored role as authoritative** — explicitly never recomputed;
3. if no local user: fetches the Clerk user, requires a **verified primary
   email**, links an existing account by email or provisions a new `CUSTOMER`;
4. never grants `OWNER` on the request path.

**This is the single synchronization point that automatic Owner recognition must
extend**, so that signup and every later sign-in share one code path.

### 2.4 Clerk helpers already present

- `_normalize_email(value)` — trim + lowercase, `None` when empty.
- `_primary_email(clerk_user)` — the address whose `id == primary_email_address_id`.
- `_is_verified(email)` — `verification.status` (str or enum) `== "verified"`.
- `_verified_primary_email(clerk_user)` — normalized verified primary email or
  `None`. Already used by bootstrap, so the recognition logic will reuse it.

---

## 3. Endpoint inventory

All routers are included in `app/main.py`. Authentication is
`require_auth` (Clerk session); authorization is a role dependency that re-reads
the **local** role every request.

| Method | Route | Router | Purpose | Auth | Authorization | Creates/syncs users | Can change roles | Tests |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| POST | `/api/v1/tickets` | tickets | Create ticket | yes | customer | no | no | test_ticket_* |
| GET | `/api/v1/tickets` | tickets | List/filter tickets | yes | user (role-scoped) | no | no | test_tickets |
| GET | `/api/v1/tickets/assigned` | tickets | Agent's assigned | yes | user | no | no | test_tickets |
| GET | `/api/v1/tickets/{id}` | tickets | Ticket detail | yes | user (scoped) | no | no | test_tickets |
| GET | `/api/v1/tickets/{id}/contact` | tickets | Staff-only phone | yes | staff | no | no | test_tickets |
| PATCH | `/api/v1/tickets/{id}` | tickets | Update ticket | yes | staff/customer (split) | no | no | test_tickets |
| POST | `/api/v1/tickets/{id}/claim` | tickets | Agent claims | yes | agent | no | no | test_assignment |
| POST | `/api/v1/tickets/{id}/assign` | tickets | Admin assigns | yes | admin | no | no | test_assignment |
| GET/POST | `/api/v1/tickets/{id}/comments` | comments | Public threads | yes | user (scoped) | no | no | test_comments |
| GET | `/api/v1/tickets/{id}/history` | ticket_history | Audit trail | yes | staff | no | no | test_history |
| GET/POST | `/api/v1/tickets/{id}/feedback` | ticket_feedback | Customer rating | yes | user/customer | no | no | test_* |
| GET/POST | `/api/v1/attachments…` | attachments | Upload/download | yes | user (scoped) | no | no | test_attachments |
| GET | `/api/v1/notifications` | notifications | List own | yes | user | no | no | test_notifications |
| GET | `/api/v1/notifications/unread-count` | notifications | Own unread | yes | user | no | no | test_notifications |
| PATCH | `/api/v1/notifications/{id}` | notifications | Mark read | yes | user (own) | no | no | test_notifications |
| POST | `/api/v1/notifications/read-all` | notifications | Mark all | yes | user | no | no | test_notifications |
| GET | `/api/v1/users/me` | users | Own profile | yes | user | **yes** (provisions on first call) | no | test_users |
| PATCH | `/api/v1/users/me` | users | Edit own profile | yes | user | no | no | test_users |
| POST | `/api/v1/users/me/avatar` | users | Sync avatar | yes | user | no | no | test_profile_photo |
| GET | `/api/v1/users` | users | Directory | yes | admin/owner | no | no | test_owner |
| GET | `/api/v1/users/{id}` | users | Inspect user | yes | admin/owner | no | no | test_owner |
| PATCH | `/api/v1/users/{id}` | users | Admin edit user | yes | admin/owner | no | **yes** (guarded) | test_owner |
| PATCH | `/api/v1/users/{id}/role` | users | Change role | yes | **owner** | no | **yes** | test_owner |
| PATCH | `/api/v1/users/{id}/status` | users | Activate/deactivate | yes | **owner** | no | indirectly | test_owner |
| GET | `/api/v1/admin/dashboard` | admin | Legacy totals | yes | admin/owner | no | no | test_admin |
| GET | `/api/v1/admin/agents` | admin | Agent list | yes | admin/owner | no | no | test_admin |
| GET | `/api/v1/admin/analytics` | analytics | Dashboard analytics | yes | admin/owner | no | no | test_analytics |
| POST/GET | `/api/v1/staff-messages…` | staff_messages | Staff↔Owner threads | yes | staff | no | no | test_staff_messages |
| POST/GET | `/api/v1/account-requests…` | account_requests | Escalations | yes | staff / admin (decide) | no | no | test_account_requests |
| GET/POST | `/api/v1/internal-messages…` | internal_messages | Owner broadcasts | yes | **owner** | no | no | test_internal_messages |

### 3.1 Endpoints that create or synchronize users

Only one: **`GET /api/v1/users/me`** (and any request that depends on
`get_current_user`), through `app/core/auth.py::get_current_user`. That is the
correct and only place to add automatic Owner recognition, so both signup and
every later request share the same logic.

### 3.2 Endpoints that can change roles

- `PATCH /api/v1/users/{id}/role` — Owner only; rejects `OWNER` as a value.
- `PATCH /api/v1/users/{id}` — Admin/Owner, guarded (`_guard_managed_user_change`);
  refuses to touch the Owner and refuses `OWNER` as a value.
- `PATCH /api/v1/users/{id}/status` — Owner only; refuses self-deactivation.

These must **not** be relaxed. Configurable ownership is a configuration-driven
transfer, not a new HTTP capability.

### 3.3 Webhooks

There is **no** Clerk webhook endpoint in the application. Registration is
synchronized synchronously on the first authenticated request. This is the
existing, reliable mechanism and the integration point.

### 3.4 Startup / lifespan

`app/main.py::lifespan`:

1. optionally `create_all` when `AUTO_CREATE_TABLES` (false in production);
2. pings the rate-limit store when enabled;
3. yields.

Owner reconciliation is **not** in the lifespan today. Deployment uses
`preDeployCommand: ["alembic upgrade head"]` (documented in
`docs/FINAL_PRODUCTION_READINESS_REPORT.md`). Adding reconciliation to startup
must not make availability depend on finding an Owner.

---

## 4. Frontend account flow

- Sign-up/sign-in are Clerk-hosted widgets (`@clerk/react`).
- The app calls `GET /api/v1/users/me` via `useMe()` after authentication; the
  response's `role` drives the entire workspace navigation.
- The frontend never submits a role. `assignable roles` exclude `owner`.
- Therefore a role change made server-side during `get_current_user` is picked
  up by the frontend on the same session's next `/users/me` fetch (the query has
  a 60 s stale time and is refetched on focus/navigation).

---

## 5. Analytics compatibility

Analytics read tickets only; ownership does not affect any aggregate. A transfer
changes one user's `role` and leaves tickets, comments, notifications, feedback
and conversations intact, so every dashboard metric is unaffected. Verified by
test in the implementation phase.

---

## 6. Supported enums (unchanged)

`Role`: customer, agent, admin, owner.
`TicketStatus`: OPEN, IN_PROGRESS, WAITING_ON_CUSTOMER, RESOLVED, CLOSED.
`TicketPriority`: LOW, NORMAL, HIGH, URGENT.
Seven ticket categories; five escalation statuses/categories; three attachment
scan states. No new values are introduced.

---

## 7. Constraints that shape the design

1. **`uq_users_single_owner`** — partial unique index on `role` where
   `role='OWNER'`. At most one Owner, ever. Every transfer must be a single
   transaction that never leaves two Owners, even momentarily.
2. **Owner is permanent in the user-management API** — `AssignableRole` excludes
   Owner; the role endpoint rejects it. Configuration is the only sanctioned way
   to move ownership.
3. **Owner cannot be demoted by another actor** over HTTP (test-covered).
4. **The Owner row must never be deleted or given a fabricated `clerk_id`.**
5. **`bootstrap_owner` refuses when an Owner exists** — so it cannot be the
   transfer mechanism; it must keep its initial-setup role.

---

## 8. Findings that drive the implementation

1. `INITIAL_ADMIN_EMAIL` is a *bootstrap-only* input, not a live identity. The
   brief requires a canonical `OWNER_EMAIL` that also drives recognition and
   transfer.
2. There is exactly one synchronization point (`get_current_user`) — the right
   place for automatic recognition.
3. There is no webhook; the synchronous flow is the reliable path.
4. `bootstrap_owner` currently duplicates promotion logic. The brief requires one
   shared service so signup and reconciliation cannot diverge.
5. Ownership transfer does not exist at all today.

---

## 9. Planned changes

1. Add `OWNER_EMAIL` to settings with **precedence rules** over the deprecated
   `INITIAL_ADMIN_EMAIL` (warn on conflict, never echo the address).
2. Create `app/services/owner_identity.py` — one shared resolver/promoter used by
   the request path, the startup reconciliation and `bootstrap_owner`.
3. Integrate recognition into `get_current_user` (verified primary email only).
4. Add an idempotent deployment-time reconciliation command and call it **after**
   migrations, non-fatally, so availability never depends on it.
5. Keep `bootstrap_owner` behaviour but route it through the shared service.
6. Tests for config, recognition, transfer, concurrency, and security.
7. Configure `OWNER_EMAIL` in Railway `helpdesk-api`/`production` with
   `--skip-deploys` (staged, not deployed).
