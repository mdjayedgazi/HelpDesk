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
#
# pg_dump/libpq do NOT understand SQLAlchemy's "postgresql+psycopg://" scheme,
# so convert it to a plain libpq URL first. This only rewrites the scheme; the
# value is still never printed.
PG_DUMP_URL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
PG_DUMP_URL="${PG_DUMP_URL/postgresql+asyncpg:/postgresql:}"

pg_dump --format=custom --no-owner --no-privileges "$PG_DUMP_URL" \
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

**Prerequisite:** an isolated target database that is **not** the production
database (a Neon branch or a separate database). The command below compares the
target's host/port/database name with the production URL and refuses when they
match, so a production URL cannot be used by accident.

### 3a. Restore from a Neon PITR branch (preferred)

1. **EXTERNAL — requires Neon access:** In the console, open the project and
   create a **branch** from the current production branch at the desired
   point in time. Neon gives the new branch its own connection string.
2. Point a staging/local `DATABASE_URL` at that branch's connection string
   (paste it into your local `.env`, never into a command line or chat).
3. Continue with the verification in section 4.

### 3b. Restore from a logical dump

```bash
: "${RESTORE_DATABASE_URL:?set RESTORE_DATABASE_URL to the isolated target}"
: "${PRODUCTION_DATABASE_URL:?set PRODUCTION_DATABASE_URL to compare against}"

# libpq does not understand SQLAlchemy's "+driver" scheme.
RESTORE_LIBPQ_URL="${RESTORE_DATABASE_URL/postgresql+psycopg:/postgresql:}"
PRODUCTION_LIBPQ_URL="${PRODUCTION_DATABASE_URL/postgresql+psycopg:/postgresql:}"

# Refuse when the target is the production database. Compare host + port +
# database name (not a substring): a production URL can contain "test" in its
# password, and a valid isolated branch need not contain any marker at all.
python - "$RESTORE_LIBPQ_URL" "$PRODUCTION_LIBPQ_URL" <<'IDENTITY'
import sys
from urllib.parse import urlsplit

def ident(url: str) -> tuple[str, int | None, str]:
    parsed = urlsplit(url)
    return (parsed.hostname or "").lower(), parsed.port, parsed.path.strip("/")

restore, production = ident(sys.argv[1]), ident(sys.argv[2])
if restore == production:
    sys.exit("Refusing: RESTORE_DATABASE_URL points at the production database")
print(f"OK: restoring into host={restore[0]} db={restore[2]!r} (not production)")
IDENTITY

# Drop/recreate only the isolated target's schema, then restore into it.
pg_restore --clean --if-exists --no-owner --no-privileges \
  --dbname "$RESTORE_LIBPQ_URL" FILE.dump
```

`--clean` drops objects in the *target* database before restoring. This is why
the identity check above and an isolated target are mandatory: the check fails
closed if the target matches production, and it does not depend on the URL
happening to contain a particular word.

## 4. Verify the restore

Run these against the restored database only. They are read-only. Reuse the
`RESTORE_LIBPQ_URL` exported in section 3b (export it again if you are in a new
shell) so the same identity you already checked is the one being read.

```bash
: "${RESTORE_LIBPQ_URL:?run section 3b first to set the verified restore URL}"
psql "$RESTORE_LIBPQ_URL" -c 'SELECT count(*) FROM users;'
psql "$RESTORE_LIBPQ_URL" -c 'SELECT count(*) FROM tickets;'
psql "$RESTORE_LIBPQ_URL" -c 'SELECT version_num FROM alembic_version;'
```

Then point a **local** backend at the restored database and confirm the
readiness probe agrees with the code it is running:

```bash
cd backend
DATABASE_URL="$RESTORE_DATABASE_URL" CLERK_SECRET_KEY=sk_test_dummy \
  FRONTEND_URL=http://localhost:5173 ENVIRONMENT=test \
  UPLOAD_DIR=/tmp/restore-drill-uploads \
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

> **Migration note:** Alembic prefers `MIGRATION_DATABASE_URL` over
> `DATABASE_URL` (see `backend/migrations/env.py`). If that variable is set,
> repoint **both** at the recovered database before running any migration,
> otherwise `alembic upgrade head` would still target the old database.

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
