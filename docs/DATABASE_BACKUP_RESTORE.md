# Database backup, restore, and disaster-recovery runbook

This runbook covers PostgreSQL backup and restore for HelpDesk. It is written
for the Neon-hosted deployment described in [`DEPLOYMENT.md`](./DEPLOYMENT.md)
and [`RAILWAY_COLLEGE_DEMO.md`](./RAILWAY_COLLEGE_DEMO.md), but the restore
procedure applies to any PostgreSQL instance.

> **This runbook does not claim any backup or restore is configured or has been
> tested.** Neon backup retention, PITR, and restore drilling require Neon
> account access. The steps that need the dashboard are marked
> **EXTERNAL — requires Neon access** and must be completed and recorded by the
> account owner. The repository cannot verify them.

## Golden rules

1. **Never restore over the live production database.** Restore into a brand
   new, isolated database (a Neon "branch" or a separate database) and verify
   it there.
2. **Never print a database URL, password, or connection string** in a shell,
   log, ticket, or commit. Use environment variables and `--stdin`/reference
   variables as shown below.
3. A backup you have never restored is not a verified backup.
4. Take a fresh manual backup immediately before any migration that changes
   existing rows (for example `0008_ticket_number_not_null`).

## 1. Determine the current backup posture (EXTERNAL — requires Neon access)

In the Neon console: **Project → Settings → Backups** (and **Restore** /
**Branches** for point-in-time restore).

Record, in the operations log (not in this repository):

| Question | Where to look | What to record |
| --- | --- | --- |
| Which plan is the project on? | Neon **Billing** | Plan determines PITR window and retention. |
| Is point-in-time recovery (PITR) enabled? | **Settings → Backups** | Yes/No and the restore window (for example 7 days). |
| What is the backup/snapshot retention? | **Settings → Backups** | Retention period. |
| Where are snapshots stored / region? | **Settings** | Region, to satisfy data-residency requirements. |
| Who can restore? | Neon **Members/Roles** | Named owners and admin roles. |

If PITR/retention is not enabled on the plan, **enable a plan that includes it
or add a scheduled logical backup (section 2) before treating the database as
production.** This is a dashboard action and cannot be done from the repository.

## 2. Scheduled logical backups (recommended independent safety net)

Even with Neon PITR, keep an independent logical backup. Run this from a
trusted, access-controlled environment, never in CI against production:

```bash
# DATABASE_URL must already be set in the environment; it is never echoed.
# --no-owner/--no-privileges make the dump portable to the restore database.
pg_dump --format=custom --no-owner --no-privileges "$DATABASE_URL" \
  > "helpdesk-$(date -u +%Y%m%dT%H%M%SZ).dump"
```

- Store the dump in encrypted object storage with a retention/versioning
  policy, not on a laptop.
- Restrict access to the storage location; the dump contains all user data.
- Verify the dump is readable (`pg_restore --list FILE`) after every run.
- A scheduled job that does this belongs to your platform, not this repository.
  If you add one, keep the credential in a secret store and never in a workflow
  file or shell history.

## 3. Restore drill (isolated database only)

**Prerequisite:** a disposable target database that is **not** the production
database. The command below refuses to run unless the target URL looks
disposable (its name contains `test`, `verify`, or `restore`).

### 3a. Restore from a Neon PITR branch (preferred)

1. **EXTERNAL — requires Neon access:** In the console, open the project and
   create a **branch** from the current production branch at the desired
   point in time. Neon gives the new branch its own connection string.
2. Point a staging/local `DATABASE_URL` at that branch's connection string
   (paste it into your local `.env`, never into a command line or chat).
3. Continue with the verification in section 4.

### 3b. Restore from a logical dump

```bash
# Refuse to run against anything that does not look disposable.
case "${RESTORE_DATABASE_URL:?set RESTORE_DATABASE_URL}" in
  *test*|*verify*|*restore*) ;;
  *) echo "Refusing: RESTORE_DATABASE_URL must name a disposable database" >&2; exit 1 ;;
esac

# Drop/recreate only the disposable database's schema, then restore into it.
pg_restore --clean --if-exists --no-owner --no-privileges \
  --dbname "$RESTORE_DATABASE_URL" FILE.dump
```

`--clean` drops objects in the *target* database before restoring. This is why
the guard above and a disposable target are mandatory.

## 4. Verify the restore

Run these against the restored database only. They are read-only.

```bash
psql "$RESTORE_DATABASE_URL" -c 'SELECT count(*) FROM users;'
psql "$RESTORE_DATABASE_URL" -c 'SELECT count(*) FROM tickets;'
psql "$RESTORE_DATABASE_URL" -c 'SELECT version_num FROM alembic_version;'
```

Then point a **local** backend at the restored database and confirm the
readiness probe agrees with the code it is running:

```bash
cd backend
DATABASE_URL="$RESTORE_DATABASE_URL" CLERK_SECRET_KEY=sk_test_dummy \
  ENVIRONMENT=test UPLOAD_DIR=/tmp/restore-drill-uploads \
  uv run python -c "
import asyncio
from app.core.health import schema_status
from app.core.database import engine
async def main():
    async with engine.connect() as c:
        print('schema:', await schema_status(c))
    await engine.dispose()
asyncio.run(main())
"
```

A restore is **verified** only when:

- the table counts are plausible for the restore point,
- `alembic_version` matches the application's expected head,
- `schema_status` prints `ok`,
- and a smoke read (`SELECT` of a known ticket/user) returns expected data.

Record the date, source backup/branch, target database, and the observed counts
in the operations log. Do not paste row contents (personal data) into logs.

## 5. After a real disaster (production restore)

1. Declare the incident and stop writes (put the API in maintenance mode or
   scale it to zero) so nothing writes to the database being replaced.
2. Restore to a **new** database/branch, verify it (section 4), then switch
   `DATABASE_URL` (Railway/Neon) to the verified database.
3. Redeploy the API so the connection pool points at the new database.
4. Confirm `GET /health/ready` returns `200` with `database: ok` and
   `schema: ok`.
5. Reconcile any writes lost between the restore point and the incident.
6. Keep the old database until the new one has served cleanly for an agreed
   window; do not delete it as the first recovery step.

## 6. Monitoring and alerting (EXTERNAL — requires platform access)

The repository exposes a readiness signal; it does not configure alerting.
Wire the following in Neon and Railway (or your monitoring provider):

| Signal | Source | Suggested alert |
| --- | --- | --- |
| API dependency readiness | `GET /health/ready` returns non-`200` | Page after 2 consecutive failures |
| Database connection saturation | Neon **Monitoring → Connections** vs. `DB_POOL_SIZE`/`DB_MAX_OVERFLOW` and replica count | Warn at ~80% of the connection limit |
| Database storage / compute | Neon **Monitoring** | Warn on sustained high storage growth or compute saturation |
| Backup/PITR status | Neon **Settings → Backups** | Alert if PITR or scheduled backups are disabled |
| Elevated 5xx | Railway logs / provider | Page on sustained rate |

Document the notification channel and on-call owner outside this repository.
