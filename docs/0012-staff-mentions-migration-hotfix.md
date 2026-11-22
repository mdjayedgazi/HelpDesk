# HelpDesk — Production Migration Hotfix: 0012 Staff Mentions

- **Date:** 2026-11-22
- **Branch:** `fix/migration-0012-canonicalize-order` (based on `main` @ `883fedf`, the merge of PR #30)
- **Scope:** one Alembic migration (`backend/migrations/versions/0012_staff_mentions.py`) and its
  PostgreSQL regression tests. No backend/frontend behaviour changes.
- **Verdict:** **FIXED — CI PASSING, AWAITING MERGE**.

---

## 1. Confirmed root cause

The deployed `0012_staff_mentions` migration renamed the participant columns and
then canonicalised participant order **before** dropping the legacy unique index
`uq_staff_conversations_staff_user`.

That index was created by migration `0004_support_workflows` with
`op.create_index(..., unique=True)` — a **standalone UNIQUE INDEX**, not a table
constraint (confirmed against the live PostgreSQL catalog, read-only: its
`pg_indexes.indexdef` reads
`CREATE UNIQUE INDEX uq_staff_conversations_staff_user ... (staff_user_id)`). It
enforced "one conversation per `staff_user_id`".

Canonicalisation rewrites each pair so `participant_a_id < participant_b_id`
(the smaller UUID first). In the real data most conversations are
staff ↔ Owner, so the Owner (whose UUID is smaller than most staff UUIDs) becomes
`participant_a_id` of many rows at once. While the old index was still active —
and now attached to the renamed column `participant_a_id` — that produced:

```
psycopg.errors.UniqueViolation:
duplicate key value violates unique constraint "uq_staff_conversations_staff_user"
DETAIL: Key (participant_a_id)=(...) already exists.
```

The single-column uniqueness rule is simply invalid for the universal model: one
person legitimately participates in many conversations, so they may be
`participant_a_id` in several. The rule that *is* correct is uniqueness of the
**pair** `(participant_a_id, participant_b_id)`.

## 2. Exact ordering defect

Original `upgrade()` order:

1. add `STAFF_MENTION` enum label (autocommit block),
2. rename `staff_user_id` → `participant_a_id`, `owner_user_id` → `participant_b_id`,
3. **UPDATE canonicalisation** ← the old unique index is still in force here,
4. drop `uq_staff_conversations_staff_user`, drop `ix_staff_conversations_owner_user_id`,
5. create the pair unique constraint + check + indexes,
6. create the mention tables.

Step 3 collided with step 4's not-yet-executed drop. The fix moves the drop to
step 1 (before rename/canonicalise):

1. **drop `uq_staff_conversations_staff_user`** (and the legacy owner index),
2. rename the columns,
3. canonicalise participants,
4. create the unique pair constraint + `a <> b` check + per-column indexes,
5. create the mention tables,
6. append the enum label (kept first for the enum, with `IF NOT EXISTS`).

## 3. Why PostgreSQL raised the error

`ALTER TABLE ... RENAME COLUMN` preserves indexes, including their definitions
(PostgreSQL rewrites the indexed column reference). So after step 2 the old
unique index still existed and now enforced uniqueness on `participant_a_id`.
The step-3 `UPDATE` set `participant_a_id` to the Owner for several rows in one
statement; the non-deferrable unique index is checked per row, so the second
such row raised `UniqueViolation`. PostgreSQL DDL is transactional, so the whole
migration rolled back — leaving `alembic_version` at `0011_query_indexes` with no
partial schema change (verified read-only on Neon).

## 4. How the fix preserves existing records

- No row is deleted, truncated, or filtered; the canonicalisation is a pure
  in-place swap of the two participant values per row.
- The old single-column index is dropped **before** the swap, so it cannot reject
  the legitimate re-orientation.
- The new pair unique constraint cannot collide for data migrated from the legacy
  model: the old per-staff uniqueness guaranteed distinct staff participants, so
  two rows can never canonicalise to the same pair.
- The `UPDATE` is deterministic and idempotent (`WHERE a > b`), and running
  `alembic upgrade head` again is a no-op (normal Alembic behaviour).
- The already-committed `STAFF_MENTION` enum label from the failed
  `autocommit_block` is tolerated via `ADD VALUE IF NOT EXISTS`.

## 5. Production database state (read-only verification)

Performed with a read-only transaction against the Neon database; **no DDL/DML**
was executed and no identifiers/credentials were printed.

| Check | Result |
| --- | --- |
| `alembic_version` | `0011_query_indexes` — the failed migration did **not** commit |
| `uq_staff_conversations_staff_user` | still present, **standalone UNIQUE INDEX** on `staff_user_id` |
| `staff_conversations` columns | `id, staff_user_id, owner_user_id, subject, created_at, updated_at, last_message_at` (unchanged) |
| Mention tables | absent (no partial schema) |
| `STAFF_MENTION` enum label | **already committed** (autocommit block does not roll back) |
| Conversations / messages | 12 / 36 rows intact |
| Rows that would canonicalise the same participant into `participant_a_id` | 7 (the collision source) |

Conclusion: Neon is **still at `0011_query_indexes`**; no production data or
schema was changed by the failed run or by this hotfix.

## 6. PostgreSQL integration tests

New `backend/tests/test_migration_0012_staff_mentions.py` (7 tests), runnable via
the repo's disposable-Postgres guard (`HD_TEST_POSTGRES_URL`, database name must
contain test/verify/ci). Each test creates and drops its **own** database, so it
is isolated and never truncates shared state. It drives Alembic directly.

| # | Scenario | Result |
| --- | --- | --- |
| 1 | Legacy data (multiple Owner conversations, UUIDs where the Owner sorts before staff and vice-versa), upgrade to head **must not** raise the UniqueViolation | pass |
| 2 | All migrated pairs satisfy `participant_a_id < participant_b_id` | pass |
| 3 | No duplicate pair; conversations + messages preserved | pass |
| 4 | Second `upgrade head` is a no-op | pass |
| 5 | Pair unique constraint rejects a duplicate pair; check rejects self-conversation; legacy index gone | pass |
| 6 | Downgrade **refuses** a staff-to-staff conversation (lossy) and leaves data intact | pass |
| 7 | Downgrade round-trips Owner-only data losslessly (legacy orientation restored, old index recreated) | pass |
| 8 | Empty database downgrades cleanly (the CI migration job's downgrade/re-upgrade step) | pass |
| 9 | Partial production state (enum label already committed) upgrades cleanly | pass |
| 10 | Mention tables + FK/indexes + `STAFF_MENTION` enum present | pass |

**Guard proof:** temporarily reverting the migration to the original ordering
made test #1 fail with the exact production error
(`UniqueViolation ... uq_staff_conversations_staff_user`); restoring the fix made
it pass. The test is a true regression guard, not a tautology.

Manual disposable-Postgres runs also verified:

- full `0011 → head` upgrade on the seeded legacy schema (4 conversations, 2
  messages seed) succeeded with all rows canonical and preserved;
- `alembic upgrade head --sql` offline SQL emits the correct order
  (`DROP INDEX … ; RENAME … ; UPDATE …`).

## 7. Backend and frontend test results

- Backend: `ruff check` pass, `ruff format --check` pass, `pyrefly` 0 errors,
  `pytest` **572 passed, 72 skipped** (the 7 new migration tests skip without
  `HD_TEST_POSTGRES_URL`).
- PostgreSQL suites in the CI order against a disposable PostgreSQL 18:
  E2E (2 passed), `test_postgres_integration` + `test_support_workflows_postgres`
  + `test_internal_messages_postgres` + `test_qa_seed_postgres` +
  `test_migration_0012_staff_mentions` (**31 passed**), demo-seed (**31 passed**).
- Migration job path on a fresh disposable DB: `alembic upgrade head`,
  `alembic check` ("No new upgrade operations detected"),
  `alembic downgrade 0008…` then `alembic upgrade head` all succeed.
- Existing behaviour re-verified: agent ↔ admin ↔ owner conversations, staff
  directory + customer rejection, structured @mentions/validation, notification
  dedupe, participant isolation, and history preservation are covered by the
  unchanged 572-test backend suite (all green).
- Frontend: `typecheck` pass, `lint` pass, **224 tests passed / 22 files**,
  production `build` pass (no frontend files changed).

## 8. Files changed

- `backend/migrations/versions/0012_staff_mentions.py` — corrected ordering,
  enum idempotency, catalog-aware legacy-index drop, lossless-downgrade guard.
- `backend/tests/test_migration_0012_staff_mentions.py` — new PostgreSQL
  regression suite (7 tests).

No other files changed. The companion `docs/universal-staff-messaging-mentions-report.md`
and project review documents are preserved.

## 9. CI and PR status

- `git diff --check` clean.
- Committed on `fix/migration-0012-canonicalize-order` (based on `main` @
  `883fedf`).
- PR opened against `main` (see PR URL). CI status is recorded on the PR; the
  `Alembic migrations (disposable PostgreSQL)` and
  `PostgreSQL integration tests` jobs exercise this change directly.

## 10. Remaining steps before the owner merges

1. Review the PR and confirm the `Alembic migrations` and `PostgreSQL
   integration` checks are green.
2. Merge the PR to `main` (do **not** manually run any migration against Neon).
3. Railway's pre-deploy step runs `alembic upgrade head` on merge; it will now
   run the corrected `0012` against Neon, which is still at `0011_query_indexes`.
4. After deploy, verify read-only: `alembic_version = 0012_staff_mentions`,
   `staff_conversations` has `participant_a_id/participant_b_id`, the legacy
   index is gone, and conversation/message counts are unchanged (12 / 36).
5. Do not `alembic stamp` to skip the failure; the corrected migration is safe to
   run over the partially-applied enum state.
