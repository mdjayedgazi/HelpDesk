# HelpDesk — Owner Identity Implementation Report

**Date:** 2026-11-21
**Branch:** `feat/configurable-owner-email`
**Base:** `main` @ `917af4b`
**Companions:** [`owner-identity-endpoint-audit.md`](./owner-identity-endpoint-audit.md),
[`owner-identity-operations.md`](./owner-identity-operations.md)

This report states what was built and what was verified. Anything not verified is
marked as such.

---

## 1. Problem

Ownership was bootstrapped once with `INITIAL_ADMIN_EMAIL`, and the request path
explicitly never recomputed a role. There was **no** way to:

- recognise a newly registered account as Owner automatically;
- move ownership when the designated person changes, without a manual database
  edit or a source change.

The audit confirmed `bootstrap_owner` refuses when an Owner exists, so it can
never be the transfer mechanism.

---

## 2. Design

### 2.1 One canonical setting

`OWNER_EMAIL` is the authority. Resolution order in `Settings.owner_email`:

1. `OWNER_EMAIL` (trimmed, lowercased);
2. deprecated `INITIAL_ADMIN_EMAIL` as a fallback when `OWNER_EMAIL` is unset;
3. otherwise `None` (automatic recognition disabled).

`owner_email_conflict` reports when both are set to *different* addresses.
`OWNER_EMAIL` still wins. The property returns a boolean only — it never exposes
either address, and no component logs an address.

### 2.2 One shared algorithm

`backend/app/services/owner_identity.py` is the only place that decides or
applies ownership:

| Function | Responsibility |
| --- | --- |
| `normalize_email` | the single trim+lowercase convention |
| `evaluate` | pure decision; makes no writes |
| `reconcile_owner` | atomic promotion/transfer with locking |
| `find_candidate_by_email` | normalized lookup of the designated account |

Every caller uses it:

- the request path (`app/core/auth.py`);
- startup (`app/main.py` lifespan);
- the deployment command (`app/commands/reconcile_owner.py`);
- the legacy bootstrap (`app/commands/bootstrap_owner.py`).

There is no second promotion algorithm.

### 2.3 Recognition on the request path

`get_current_user` already had the only user-synchronisation logic. It now calls
`_reconcile_owner_for` in two places:

1. an **existing** local user, before returning them;
2. a **freshly provisioned or newly linked** user, reusing the Clerk object it
   already fetched (no second API call).

Recognition is a no-op unless `OWNER_EMAIL` is set and the identity's **verified
Clerk primary email** matches it.

### 2.4 Deployment reconciliation

`app/main.py::lifespan` performs one best-effort reconciliation after schema
availability and before readiness. A missing designated account or a Clerk
outage logs a sanitized warning and **never** fails or delays startup.

`python -m app.commands.reconcile_owner` is the operator/deploy equivalent:

| Situation | Exit | Effect |
| --- | --- | --- |
| `OWNER_EMAIL` unset | 2 | nothing |
| designated account not registered | 0 | ownership preserved |
| already the Owner | 0 | nothing |
| promoted / transferred | 0 | applied atomically |
| constraint / transaction failure | 1 | rolled back |
| Clerk unreachable | 0 | ownership preserved |

`--json` emits `{"status": ..., "changed": ...}`.

---

## 3. Clerk verification (the security core)

Promotion requires **all** of:

1. a Clerk identity resolved from the trusted token `sub` (never the request body);
2. `clerk.users.get_async(user_id=...)` returning the authoritative user record;
3. that record's `primary_email_address_id` pointing at an address whose
   verification status is `verified`;
4. the normalized address equalling the normalized `OWNER_EMAIL`;
5. the local account being **active**.

Rejected by construction:

- an email submitted by the registration form;
- a client-supplied role;
- a secondary email address;
- an unverified address;
- Clerk metadata;
- a cached local email (the local row's email is never compared — only Clerk's
  verified primary address is).

When Clerk cannot be reached, `evaluate` returns `identity_unavailable` and
nothing changes.

---

## 4. Transaction and locking

`reconcile_owner`:

1. takes a **transaction-scoped PostgreSQL advisory lock**
   (`pg_advisory_xact_lock`, key `20261122`) — released on commit/rollback;
2. selects the target and the previous Owner `FOR UPDATE`;
3. **demotes the previous Owner to `ADMIN` and flushes**, then promotes the
   target and flushes — so the partial unique index never observes two Owners;
4. commits as one unit; any exception rolls back everything.

SQLite (tests) serialises writers itself; the lock is skipped there. The
`uq_users_single_owner` partial unique index remains the final guarantee.

---

## 5. Previous Owner behaviour

- Role becomes `ADMIN`; the row is otherwise untouched.
- `is_active` stays `true`; `clerk_id` is unchanged.
- Tickets, comments, notifications, feedback and conversations are untouched.
- No delete, no deactivate, no identity rewrite.

`ADMIN` keeps every administrative capability except role/status management,
which is Owner-only (`can_manage_users`). This is documented explicitly in the
operations guide.

---

## 6. Tests executed

| Suite | Result |
| --- | --- |
| Full backend suite (`pytest -q`) | **518 passed**, 64 skipped (opt-in PG/Redis) |
| `tests/test_owner_identity.py` (SQLite + Clerk doubles) | 30 passed |
| `tests/test_owner_identity_postgres.py` (disposable PG 16) | 6 passed |
| `ruff check` / `ruff format --check` | clean |

The PostgreSQL suite proves, on a real database:

- the real `uq_users_single_owner` index exists and is partial (`WHERE (role …)`);
- promotion and transfer leave exactly one Owner;
- five concurrent reconciliations converge to **one** Owner (advisory lock);
- a forced persistence failure rolls back, restoring the previous Owner;
- a transfer preserves the prior Owner's tickets and comments byte-for-byte.

The SQLite suite covers configuration resolution and precedence, every
recognition decision, transfer semantics, idempotency, and the security cases
(customer/agent/admin escalation attempts, `owner` rejected as an assignable
value, unverified email, Clerk failure, inactive account).

---

## 7. API regression

The existing 488 tests continued to pass before the new tests were added, so the
endpoint inventory in the audit is unchanged. The only behavioural change on the
request path is that an account matching `OWNER_EMAIL` with a verified primary
email becomes Owner; every other role and every endpoint behaves exactly as
before.

---

## 8. Railway configuration

`OWNER_EMAIL` was set on `helpdesk-api` / `production` using the Railway CLI with
`--skip-deploys`, so the value is **staged** and no deployment was triggered. The
exact verification results are in the final report at the end of `data.md`.

`INITIAL_ADMIN_EMAIL` did not exist on the service, so no deprecated value needed
to be reconciled.

---

## 9. Activation status

The production behaviour is **not live**. It becomes active only when this branch
is merged to `main` and Railway deploys the merged commit. Until then the staged
variable is inert.

---

## 10. Limitations

1. **No live production verification** — the behaviour was verified by tests, not
   by signing in as the designated Owner on production (that requires the merge
   and deploy).
2. **No webhook** — recognition is synchronous on the first authenticated
   request. That is the existing reliable path; nothing new was added.
3. **The designated person must register and verify** before recognition. Until
   then the previous Owner is preserved — by design.
4. **SQLite cannot prove concurrency**; that is why the PostgreSQL suite exists.
