# HelpDesk — Owner Identity Operations Guide

This guide is for the operator who runs HelpDesk. It explains how ownership works
and how to hand the product to a different Owner **without changing source code**.

---

## 1. How ownership is decided

One backend variable decides ownership:

```
OWNER_EMAIL=<the person's email>
```

The backend compares it to the **verified Clerk primary email** of every account
it synchronises. When they match and the account is active, that account becomes
the single `OWNER`.

Rules the backend enforces for you:

- unverified email → not promoted;
- secondary (non-primary) email → not promoted;
- inactive account → not promoted;
- Clerk unavailable → nothing changes;
- exactly one Owner, always.

The stored database role remains the authority for permissions. Clerk metadata is
never used for authorisation.

---

## 2. First-time setup

1. The person signs up / signs in **once** through the app (Clerk). This creates
   their local account.
2. In Railway → `helpdesk-api` → `production` → Variables, set
   `OWNER_EMAIL` to their verified primary email.
3. Redeploy (or wait for the next deploy) so the new configuration is loaded.

From then on they are recognised automatically on sign-in. You can also force it
immediately without a deploy:

```bash
cd backend
python -m app.commands.reconcile_owner        # add --json for machine output
```

It is safe to run repeatedly.

> The legacy `INITIAL_ADMIN_EMAIL` still works as a fallback when `OWNER_EMAIL` is
> unset, but prefer `OWNER_EMAIL`. If both are set to different addresses,
> `OWNER_EMAIL` wins and a sanitized warning is logged (no address is printed).

---

## 3. Automatic recognition on registration

When someone registers with the configured email and verifies it, the very first
authenticated request promotes them. No operator action is needed.

If they register with any other email they remain a normal user; a secondary email
matching the configuration does **not** count.

---

## 4. Moving ownership to a new person (company handover)

You only change one value. **Do not** edit the database by hand.

1. The new person signs up and **verifies** their email. (They must exist as a
   local account; the backend will not invent one.)
2. In Railway → `helpdesk-api` → `production` → Variables, change `OWNER_EMAIL`
   to the new person's verified primary email.
3. Redeploy, or run `python -m app.commands.reconcile_owner` in that environment.
4. Verify with:

   ```bash
   python -m app.commands.reconcile_owner --json
   # {"status": "transferred", "changed": true}
   ```

What happens:

| Before | After |
| --- | --- |
| Previous person: `OWNER` | Previous person: `ADMIN` |
| New person: e.g. `CUSTOMER` | New person: `OWNER` |
| One Owner | Still exactly one Owner |

The previous person is **not** deleted or deactivated, and their Clerk identity is
not touched. Their tickets, comments, notifications and conversations remain
theirs. They keep administrator-level access; they simply lose the
Owner-exclusive abilities (changing roles and account status, and composing
Owner broadcasts).

### If the new person has not registered yet

Nothing happens and nothing breaks. The current Owner is preserved. As soon as
the new person registers and verifies their email, the next authenticated request
transfers ownership automatically.

---

## 5. What never happens

- No account is created on your behalf; nobody is promoted without signing in.
- No `clerk_id` is ever written by a command; only Clerk can establish that.
- No role is changed by a client request. Customers cannot make themselves Owner;
  agents and admins cannot either; `owner` is rejected as an assignable role.
- Ownership is never granted from an unverified or secondary email, or from Clerk
  metadata.
- There is never more than one Owner — the database enforces this with a partial
  unique index, and every change is a single transaction.

---

## 6. Requiring the previous Owner to step back completely

Demotion to `ADMIN` is the documented default. If you want the previous person to
have **no** access at all, deactivate their account from the Owner's user
management screen (the new Owner can do this). Deactivation is separate from
ownership and is reversible; it is not done automatically.

---

## 7. Troubleshooting

| Symptom | Likely cause | Action |
| --- | --- | --- |
| New person is still a normal user | Email not verified in Clerk, or set as a secondary address | Have them verify and make it primary |
| `reconcile_owner` says `target_missing` | They have not signed in yet | They sign up / sign in once, then retry |
| `reconcile_owner` says `target_inactive` | Their local account is deactivated | Reactivate it, then retry |
| `reconcile_owner` says `identity_unavailable` | Clerk could not be reached | Retry shortly; ownership is preserved meanwhile |
| `OWNER_EMAIL` unset | No configured owner | Set the variable; automatic recognition is otherwise disabled |
| Both variables set, warning logged | Legacy + new configured differently | Clear `INITIAL_ADMIN_EMAIL`; `OWNER_EMAIL` is authoritative |

---

## 8. Deployment safety

- Ownership reconciliation runs at startup **best-effort**: a missing designated
  account or a Clerk outage never blocks or fails a deploy.
- The existing `alembic upgrade head` pre-deploy step is unchanged; reconciliation
  happens after the schema is available.
- The `reconcile_owner` command is idempotent and safe to run from an automated
  release step.

---

## 9. Environment variables

| Variable | Required | Purpose |
| --- | --- | --- |
| `OWNER_EMAIL` | recommended | Canonical Owner identity |
| `INITIAL_ADMIN_EMAIL` | deprecated | Fallback when `OWNER_EMAIL` is unset |

Set the real address in the deployment configuration (Railway service
variables), never in a committed file. `backend/.env.example` contains only the
placeholder `owner@example.com`.
