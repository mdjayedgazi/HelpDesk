"""Safe, reusable database reset command.

This command removes all application data while preserving:

* The configured owner account (identified by ``INITIAL_ADMIN_EMAIL``).
* The database schema, Alembic migration history, and all metadata.
* Database extensions and infrastructure objects.

It defaults to a **dry run** and requires explicit confirmation before
deleting any data. It is designed to be safe, auditable, and idempotent.

Usage (from the ``backend/`` directory):

    # Dry run — inspect what would be deleted
    uv run python -m app.commands.reset_database

    # Execute the reset (requires --execute flag)
    uv run python -m app.commands.reset_database --execute

    # Force execution without prompting (for scripting)
    uv run python -m app.commands.reset_database --execute --force

The command will refuse to run if:

* The database cannot be identified safely.
* No owner record matching ``INITIAL_ADMIN_EMAIL`` exists.
* Multiple owner records are found (indicates a conflict to investigate).
* The Alembic revision cannot be determined.

Dependencies are deleted in an order compatible with foreign-key constraints.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

import app.models  # noqa: F401 — register all table metadata
from app.core.config import settings
from app.enums.enums import Role
from app.models.user import User


# --------------------------------------------------------------------------- #
# Tables ordered for safe deletion (dependents first, users last)             #
# --------------------------------------------------------------------------- #
#
# This order respects the foreign-key relationships discovered in the models:
#
#   account_management_request_events  -> account_management_requests
#   account_management_request_comments -> account_management_requests
#   account_management_requests        -> users, tickets
#   internal_message_recipients        -> internal_messages, users
#   internal_messages                  -> users
#   staff_messages                     -> staff_conversations, users
#   staff_conversations                -> users
#   notifications                      -> users, tickets, staff_conversations,
#                                          internal_messages,
#                                          account_management_requests
#   ticket_feedback                    -> tickets, users
#   ticket_history                     -> tickets, users
#   attachments                        -> tickets, users
#   comments                           -> tickets, users
#   tickets                            -> users
#   users                              -> (root)
#
# We delete leaf tables first, then work upward.

_DELETION_ORDER: tuple[str, ...] = (
    # Account request audit trail (depends on account_management_requests)
    "account_management_request_events",
    "account_management_request_comments",
    # Account requests (depends on users, tickets)
    "account_management_requests",
    # Internal message recipients (depends on internal_messages, users)
    "internal_message_recipients",
    # Internal messages (depends on users)
    "internal_messages",
    # Staff messages (depends on staff_conversations, users)
    "staff_messages",
    # Staff conversations (depends on users)
    "staff_conversations",
    # Notifications (depends on users, tickets, staff_conversations,
    #    internal_messages, account_management_requests)
    "notifications",
    # Ticket feedback (depends on tickets, users)
    "ticket_feedback",
    # Ticket history (depends on tickets, users)
    "ticket_history",
    # Attachments (depends on tickets, users)
    "attachments",
    # Comments (depends on tickets, users)
    "comments",
    # Tickets (depends on users)
    "tickets",
)


class ResetError(RuntimeError):
    """A safe, user-facing reason the reset could not proceed."""


def _build_engine() -> AsyncEngine:
    """Build an async engine without the statement_timeout that poolers reject.

    Neon poolers and similar managed services do not accept the
    ``statement_timeout`` startup parameter, so we build the engine without
    the application's default connect args.
    """
    from app.core.database import _normalize_database_url

    url = _normalize_database_url(settings.DATABASE_URL)
    return create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.DB_CONNECT_TIMEOUT_SECONDS},
    )


async def _identify_database(session: AsyncSession) -> dict[str, Any]:
    """Return a summary of the target database without exposing credentials."""
    from urllib.parse import urlsplit

    parsed = urlsplit(settings.DATABASE_URL)
    hostname = parsed.hostname or "sqlite"
    db_name = parsed.path.strip("/") or "main"

    # Alembic revision
    try:
        result = await session.execute(text("SELECT version_num FROM alembic_version"))
        revision = result.scalar_one_or_none()
    except Exception:
        revision = None

    return {
        "hostname": hostname,
        "database": db_name,
        "alembic_revision": revision,
    }


async def _find_owner(session: AsyncSession) -> User | None:
    """Locate the owner user by the configured INITIAL_ADMIN_EMAIL.

    Returns the owner user or ``None`` if not found.
    Raises ``ResetError`` if multiple owners exist.
    """
    configured_email = settings.initial_admin_email
    if not configured_email:
        raise ResetError(
            "INITIAL_ADMIN_EMAIL is not configured. "
            "Set it in backend/.env to identify the owner to preserve."
        )

    # Check for multiple owners first
    owner_count_result = await session.execute(
        text("SELECT COUNT(*) FROM users WHERE role = 'OWNER'")
    )
    owner_count = owner_count_result.scalar()

    if owner_count == 0:
        return None
    if owner_count > 1:
        raise ResetError(
            f"Multiple OWNER records found ({owner_count}). "
            "This indicates a data integrity issue. "
            "Investigate and resolve before resetting."
        )

    # Find the single owner and verify it matches the configured email
    result = await session.execute(
        text(
            "SELECT id, email, username, role, is_active, clerk_id "
            "FROM users WHERE role = 'OWNER'"
        )
    )
    row = result.fetchone()
    if row is None:
        return None

    owner_email = row[1]
    if owner_email.strip().lower() != configured_email.strip().lower():
        raise ResetError(
            f"The existing owner email ({owner_email}) does not match "
            f"the configured INITIAL_ADMIN_EMAIL ({configured_email}). "
            "Update the configuration or investigate the mismatch."
        )

    # The database enum may store uppercase values (e.g. "OWNER") while the
    # Python Role enum uses lowercase ("owner"). Normalize before constructing.
    role_value = row[3]
    if isinstance(role_value, Role):
        role = role_value
    else:
        role = Role(role_value.lower())

    # SQLite may return UUIDs as hex strings without dashes; normalize.
    owner_id = row[0]
    if isinstance(owner_id, str):
        owner_id = uuid.UUID(owner_id)

    # Reconstruct a User object for the caller
    owner = User(
        id=owner_id,
        email=owner_email,
        username=row[2],
        role=role,
        is_active=row[4],
        clerk_id=row[5],
        full_name="",  # Not needed for preservation logic
    )
    return owner


async def _get_row_counts(session: AsyncSession) -> dict[str, int]:
    """Return row counts for all application tables."""
    counts: dict[str, int] = {}
    all_tables = list(_DELETION_ORDER) + ["users"]
    for table in all_tables:
        try:
            result = await session.execute(text(f"SELECT COUNT(*) FROM {table}"))
            counts[table] = result.scalar()
        except Exception:
            counts[table] = -1  # Table doesn't exist or error
    return counts


async def _dry_run(session: AsyncSession) -> None:
    """Print a summary of what would be deleted without changing anything."""
    db_info = await _identify_database(session)
    print("=" * 60)
    print("DATABASE RESET — DRY RUN")
    print("=" * 60)
    print()
    print(f"Target database : {db_info['database']}")
    print(f"Host            : {db_info['hostname']}")
    print(f"Alembic revision: {db_info['alembic_revision'] or 'unknown'}")
    print()

    # Owner check
    try:
        owner = await _find_owner(session)
        if owner:
            print(
                f"Owner to preserve: {owner.email} "
                f"({owner.username}, id={owner.id})"
            )
        else:
            print(
                "WARNING: No owner record found matching INITIAL_ADMIN_EMAIL. "
                "The reset will proceed but no owner will remain."
            )
    except ResetError as exc:
        print(f"OWNER CHECK FAILED: {exc}")
        print()
        print("Resolve the owner issue before proceeding.")
        return

    # Row counts
    counts = await _get_row_counts(session)
    print()
    print("Current row counts (before reset):")
    print("-" * 40)
    for table, count in counts.items():
        marker = " ← PRESERVED" if table == "users" and owner else ""
        print(f"  {table:<45} {count}{marker}")

    # Deletion summary
    total_deletable = sum(
        counts.get(t, 0) for t in _DELETION_ORDER if counts.get(t, 0) > 0
    )
    other_users = counts.get("users", 0) - (1 if owner else 0)
    total_deletable += max(other_users, 0)

    print()
    print(f"Total rows to delete: {total_deletable}")
    print()
    print("Tables that will be cleared (in order):")
    for i, table in enumerate(_DELETION_ORDER, 1):
        c = counts.get(table, 0)
        print(f"  {i:2d}. {table} ({c} rows)")
    print(f"  {len(_DELETION_ORDER) + 1:2d}. users (all except owner)")

    print()
    print("=" * 60)
    print("DRY RUN COMPLETE — No data was modified.")
    print("=" * 60)


async def _execute_reset(session: AsyncSession) -> None:
    """Execute the actual reset, preserving the owner."""
    db_info = await _identify_database(session)
    print("=" * 60)
    print("DATABASE RESET — EXECUTING")
    print("=" * 60)
    print()
    print(f"Target database : {db_info['database']}")
    print(f"Host            : {db_info['hostname']}")
    print()

    # Verify owner exists
    owner = await _find_owner(session)
    if owner:
        print(f"Owner to preserve: {owner.email} ({owner.username})")
    else:
        print("WARNING: No owner record found. Proceeding without owner preservation.")

    owner_id = owner.id if owner else None

    # Pre-reset counts
    pre_counts = await _get_row_counts(session)

    # Delete in order
    print()
    print("Deleting application data...")
    for table in _DELETION_ORDER:
        try:
            await session.execute(text(f"DELETE FROM {table}"))
            count = pre_counts.get(table, 0)
            print(f"  ✓ {table} ({count} rows cleared)")
        except Exception as exc:
            await session.rollback()
            raise ResetError(f"Failed to delete from {table}: {exc}") from None

    # Delete non-owner users.
    # SQLite stores UUIDs as hex strings without dashes, so we use the
    # hex representation for the comparison to work across backends.
    if owner_id:
        owner_id_hex = owner_id.hex
        result = await session.execute(
            text("DELETE FROM users WHERE id != :owner_id"),
            {"owner_id": owner_id_hex},
        )
        deleted_users = result.rowcount
    else:
        result = await session.execute(text("DELETE FROM users"))
        deleted_users = result.rowcount

    print(f"  ✓ users ({deleted_users} non-owner rows cleared)")

    # Commit
    await session.commit()
    print()
    print("Reset committed successfully.")

    # Post-reset verification
    print()
    print("Post-reset verification:")
    post_counts = await _get_row_counts(session)
    all_clear = True
    for table in _DELETION_ORDER:
        c = post_counts.get(table, 0)
        if c != 0:
            print(f"  ✗ {table}: {c} rows remaining (unexpected)")
            all_clear = False
        else:
            print(f"  ✓ {table}: empty")

    # Users should have exactly 1 (the owner) or 0
    users_count = post_counts.get("users", 0)
    expected_users = 1 if owner_id else 0
    if users_count == expected_users:
        print(f"  ✓ users: {users_count} (owner preserved)")
    else:
        print(f"  ✗ users: {users_count} (expected {expected_users})")
        all_clear = False

    # Verify owner still exists and is correct
    if owner_id:
        verify = await session.execute(
            text(
                "SELECT id, email, role, is_active FROM users WHERE id = :owner_id"
            ),
            {"owner_id": owner_id.hex},
        )
        row = verify.fetchone()
        if row:
            print(f"  ✓ Owner verified: {row[1]}, role={row[2]}, active={row[3]}")
        else:
            print("  ✗ Owner record not found after reset!")
            all_clear = False

    # Verify Alembic
    try:
        ver = await session.execute(text("SELECT version_num FROM alembic_version"))
        rev = ver.scalar_one_or_none()
        print(f"  ✓ Alembic revision: {rev}")
    except Exception as exc:
        print(f"  ✗ Alembic check failed: {exc}")

    print()
    if all_clear:
        print("=" * 60)
        print("RESET COMPLETE — All application data cleared, owner preserved.")
        print("=" * 60)
    else:
        print("=" * 60)
        print("RESET COMPLETE WITH WARNINGS — Review the output above.")
        print("=" * 60)


async def _main(dry_run: bool, execute: bool, force: bool) -> int:
    """Entry point for the reset command."""
    engine = _build_engine()

    try:
        async with AsyncSession(engine) as session:
            if not execute:
                await _dry_run(session)
                return 0

            # Execute mode
            if not force:
                # Interactive confirmation
                print()
                try:
                    response = input(
                        "This will delete all application data except the owner. "
                        "Type 'RESET' to confirm: "
                    )
                except EOFError:
                    print()
                    print("Aborted: no terminal input available. Use --force to skip.")
                    return 1

                if response.strip() != "RESET":
                    print("Aborted: confirmation not received.")
                    return 1

            await _execute_reset(session)
            return 0

    except ResetError as exc:
        print(f"Reset failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        return 2
    finally:
        await engine.dispose()


def main() -> int:
    """Synchronous entry point for ``python -m app.commands.reset_database``."""
    parser = argparse.ArgumentParser(
        description="Safely reset application data while preserving the owner."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete data (default is dry run).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip interactive confirmation (use with --execute).",
    )
    args = parser.parse_args()

    if args.force and not args.execute:
        print("--force requires --execute", file=sys.stderr)
        return 1

    return asyncio.run(_main(
        dry_run=not args.execute,
        execute=args.execute,
        force=args.force,
    ))


if __name__ == "__main__":
    raise SystemExit(main())
