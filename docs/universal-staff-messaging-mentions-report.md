# HelpDesk — Universal Staff Messaging & @Mentions Report

- **Date:** 2026-11-22
- **Branch:** `feat/universal-staff-mentions`
- **Base:** `main` @ `819a765` (after PR #29 merged)
- **PR target:** `main`
- **Scope:** backend (`staff-messages`, `internal-messages`, notifications) and the
  staff messaging frontend. One additive Alembic migration. No Neon changes, no
  destructive operations.
- **Verdict:** **IMPLEMENTED AND CI VERIFIED — AWAITING MERGE**.

---

## 1. Original messaging limitations

The internal messaging system was **Owner-centric** by design:

- `staff_conversations` stored a fixed `(staff_user_id, owner_user_id)` pair with
  a unique index on `staff_user_id`, so the only possible topology was one
  thread per staff member ↔ the single Owner.
- The router rejected any conversation started by the Owner
  (`403 "Only agents and admins start conversations with the Owner"`).
- Agents and admins could therefore only talk to the Owner, never to each other
  or to another admin.
- The staff directory endpoint (`/internal-messages/recipients`) was
  **Owner-only** (`owner_dependency`).
- There was **no @mention** capability at all.

## 2. Existing architecture findings

- `staff_conversations` / `staff_messages`: participant-scoped 1:1 threads;
  `staff_messages.read_at` tracks the recipient's read state; N+1-safe bulk
  summaries already existed and were preserved.
- `internal_messages` / `internal_message_recipients`: Owner broadcast/direct
  compose with per-recipient read state.
- Notifications are created in `services/notifications.py`, with deep links via
  `related_conversation_id` / `related_internal_message_id`.
- `staff_dependency` already allowed AGENT/ADMIN/OWNER; the *start* logic and
  the *directory* endpoint were the role restrictions, not the dependency.

## 3. New role-permission model

| Operation | OWNER | ADMIN | AGENT | CUSTOMER |
| --- | --- | --- | --- | --- |
| Open staff messaging (list conversations) | Yes | Yes | Yes | No (403) |
| Search eligible staff directory | Yes | Yes | Yes | No (403) |
| Start staff conversation | Yes | Yes | Yes | No (403) |
| Send staff messages | Yes | Yes | Yes | No (403) |
| Mention staff members | Yes | Yes | Yes | No (403) |
| Read authorized conversation | Yes | Yes | Yes | No (403/404) |

Customers are excluded at the router dependency (`403`). An employee can only
read/reply to conversations they participate in; another employee's thread is
`404` (never `403`) so its existence is not revealed. Role comes only from the
authenticated Clerk identity → locally verified account, never the client.

## 4. Employee directory search

`GET /api/v1/staff-messages/directory` (any staff role):

- Returns active AGENT/ADMIN/OWNER accounts, **excluding the caller** and all
  customers and inactive accounts.
- Search matches display name, username and account id, **case-insensitively**,
  and accepts an `@`-prefixed query (stripped).
- Ranking: exact username first, then usernames/names that start with the query,
  then other partial matches (`case(...)` sort key, portable to SQLite).
- Bounded by `limit` (1–100) + `offset`.
- Customers receive `403`; the endpoint is never reachable from customer UI.

## 5. Case-insensitive autocomplete

The composer triggers on `@` at the caret and sends the typed query to the
directory. Because both sides are normalized (frontend sends the raw query; the
backend uses `ilike`/`lower()`), `@A`, `@a`, `@AL`, `@al`, `@Ali`, `@ali`,
`@ALICE`, `@alice` all discover the same matching employees. Verified in a real
browser: `@A` and `@a` returned the same suggestion list, and selecting one
inserted `@<username> ` with a trailing space and restored the caret.

Autocomplete does **not** trigger inside email addresses (`name@host`), does not
trigger when the caret is away from the `@`, and supports multiple mentions.

## 6. Employee identification fields shown

Each suggestion shows: avatar/initials, full name, `@username`, role badge, and
a short account id (`ID xxxxxxxx`). No email, Clerk id, tokens or other
sensitive data is exposed. Duplicate names are distinguishable by username + id.

## 7. Structured mention persistence

- New tables `staff_message_mentions` and `internal_message_mentions`: one row
  per `(message_id, mentioned_user_id)`, both foreign keys to `users.id`, with a
  unique constraint so a duplicate mention of the same person in one message is
  stored once.
- The message body keeps the readable `@username`; correctness never depends on
  parsing it. The send payload carries `mentioned_user_ids` (real ids).
- Backend validation on send: the mentioned user must exist, be **active**, hold
  a **staff role**, and not be the sender. Unknown ids → `422`; inactive/customer
  → `422`; self-mention → `422`. Invalid mentions abort the whole send (nothing
  is stored).
- The frontend only submits mentions whose `@username` still appears in the final
  body, so editing the text out drops the structured mention.

## 8. Notification implementation

- Mention notifications use a new `STAFF_MENTION` value on the existing
  `notificationtype` enum, in the existing `MESSAGE_TYPES` category and the
  frontend icon/type maps.
- Notifications are created **only after** the message rows are staged for the
  same transaction (persist-on-commit); typing never creates anything.
- **Exactly one notification per message per person.** In a 1:1 thread the
  counterpart gets one notification: typed `STAFF_MENTION` if they were
  mentioned, otherwise `STAFF_MESSAGE_RECEIVED`. In an Owner-composed message an
  addressed recipient gets one notification: `STAFF_MENTION` if mentioned, else
  `INTERNAL_MESSAGE_RECEIVED`. A person mentioned twice in one message is
  notified once (one mention row).
- **Only reachable mentions are notified.** A mentioned employee who cannot open
  the message is not notified — e.g. a third party in a 1:1 thread, or a
  broadcast recipient outside the addressed audience. A notification there would
  deep-link to something they cannot read (a 404) and would leak a private
  thread's existence. The structured mention row is still stored for rendering.
- Customers are never notified about internal mentions (they cannot reach the
  channel and the recipient ids are validated staff accounts).
- Notifications deep-link to the conversation/message via the existing fields.

## 9. Reusable composer implementation

- `StaffMentionComposer` — a self-contained composer with the suggestion panel,
  used by the 1:1 conversation panel.
- `MentionBodyEditor` — a controlled textarea with the same autocomplete, used by
  the Owner compose form (which owns its own review/send flow).
- `StaffConversationPicker` — the teammate selector for starting a conversation.
- Both composers share the pure helpers in `lib/mentions.ts`
  (`activeMention`, `insertMention`, `highlightMatch`) and the staff-only
  `useStaffDirectory` hook, so the logic exists once.
- `StartConversationDialog` is shared by the agent/admin workspace and the Owner
  inbox, so **every** staff role can start a conversation.

Accessibility: `role="combobox"` + `aria-expanded` + `aria-controls` on the
textarea; `role="listbox"`/`role="option"` + `aria-selected` on suggestions;
`aria-activedescendant` tracks the highlighted option; ArrowUp/Down move,
Enter/Tab select, Escape closes; Enter only sends when the panel is closed;
`onMouseDown` is prevented on the panel so mouse/touch selection works and focus
stays in the composer.

## 10. Security and authorization tests

`backend/tests/test_staff_mentions.py` (24) + `tests/test_staff_messages.py` (21)
cover: customer denied everywhere (messaging + directory), every staff pairing
can converse, self-conversation rejected, customer/inactive/unknown recipient
rejected, participant isolation (404 for non-participants), spoofed sender/ids
rejected (422), duplicate pair impossible, mention of unknown/inactive/customer/
self rejected, mention persistence, duplicate-in-one-message stored once,
mention notifications and dedupe, customer never notified, Owner-compose
mention persist + dedupe, and the full role matrix.

## 11. Test results

- Backend: `ruff check` pass, `ruff format --check` pass, `pyrefly` 0 errors,
  `pytest` **571 passed, 65 skipped**.
- Frontend: `typecheck` pass, `lint` pass, **224 passed / 22 files** (was 196),
  production `build` pass.
- New frontend tests: `lib/mentions.test.ts` (18) and
  `components/StaffMentionComposer.test.tsx` (10: `@` opens, `@A` query passed,
  selection inserts handle + real id, two mentions, Arrow+Enter selects not
  sends, Escape closes, empty/loading/error states, mention dropped when text
  removed).
- Migration verified on a disposable PostgreSQL 18: `upgrade head` →
  `downgrade 0011` → `upgrade head`, with a seeded legacy row confirming the
  canonical backfill (`participant_a_id < participant_b_id`) and no data loss.

## 12. Accessibility and responsive verification

Keyboard and screen-reader roles as above. The suggestion panel is absolutely
positioned above the composer (no layout shift) and scrolls internally on small
height. In-browser verification (Playwright, 1366px): typing `@`, `@A`, `@a`
opened the panel with the expected employees; selecting inserted the handle with
a trailing space; the Owner inbox "New message" opened the teammate picker
dialog. No console errors from the app (the only browser console noise came from
un-stubbed harness endpoints falling through to a non-running local API).

## 13. Migration details

`migrations/versions/0012_staff_mentions.py`:

- Renames `staff_conversations.staff_user_id/owner_user_id` →
  `participant_a_id/participant_b_id` and normalizes rows to canonical
  (`a < b`) order — **existing conversations and messages are preserved**;
  impossible to collide because the old per-staff unique index guaranteed
  distinct participants.
- Replaces the single-participant unique index with a unique **pair** constraint
  + a `participant_a_id <> participant_b_id` check + per-column indexes.
- Creates `staff_message_mentions` and `internal_message_mentions`.
- Appends `STAFF_MENTION` to `notificationtype` (PostgreSQL `autocommit_block`,
  `IF NOT EXISTS`).
- `downgrade` restores the old column names/constraints and drops the new
  objects; the `STAFF_MENTION` enum label is left in place (Postgres cannot
  remove an enum value; harmless when unused). Verified round-trip.

No migration was run against Neon.

## 14. Git branch and commits

- Branch: `feat/universal-staff-mentions` (from `main` @ `819a765`; the prior
  width/motion and pagination work were already merged, so the tree started clean
  apart from the untracked verification harness).
- Commits: `38fddca` (implementation) and `37760e7` (PostgreSQL-suite updates
  for the participant model).

## 15. Pull request URL

**https://github.com/mdjayedgazi/HelpDesk/pull/30** (targets `main`, all checks
passing).

## 16. CI status

All PR checks pass: Backend lint + SQLite tests, Frontend typecheck/lint/tests/
build, **Alembic migrations**, **PostgreSQL integration**, Docker image builds,
Production dependency audit, Helm validation, Static security + secret scan,
CodeQL, Trivy.

The PostgreSQL-opt-in suites (skipped locally without a test database) initially
failed in CI because two files still used the old conversation shape; both were
updated (`test_support_workflows_postgres.py`, `test_demo_seed_postgres.py`) and
verified against disposable PostgreSQL 18 in the exact CI order (E2E first, then
the PG suites, then the demo-seed suite).

## 17. Deployment status

**Not deployed. Awaiting review and merge.**

- Touches **both** `helpdesk-api` (models, services, routers, migration) and
  `helpdesk-web` (frontend). They must deploy together.
- **A migration is required:** `0012_staff_mentions`. Railway's established
  pre-deployment migration step runs it through the approved release path; do not
  run it manually against production.
- Order: API (runs the migration, then serves the new schema) → web. Because the
  frontend depends on the new conversation shape, the API must be live before or
  with the web deploy, which is the normal single-merged-commit path.
- Post-deployment checklist:
  1. `/health/ready` 200; `alembic current` shows `0012_staff_mentions`.
  2. `GET /staff-messages/directory` works for an agent; `403` for a customer.
  3. An agent can start and message an admin, and vice-versa.
  4. Typing `@` in a conversation (and in Owner compose) shows active staff.
  5. A mentioned employee receives one notification; the counterpart gets no
     duplicate.
  6. Existing conversations/messages are still present after the migration.

## Known scope notes

- The Owner Inbox keeps its "Compose broadcast" flow (Owner → audience) and the
  new universal 1:1 threads; both now support mentions. The `OwnerInbox` inbox
  no longer offers the old role/sender filter controls because the backend
  conversation list is scoped to the caller's participant pairs (an Owner sees
  exactly their threads); an "Unread only" filter remains.
- Offset-free concerns are out of scope; the conversation list is bounded by
  `limit/offset`.
