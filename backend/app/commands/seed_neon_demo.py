"""Seed the *Neon development* database with clearly-marked QA/demo records.

This command exists so the Owner can sign in to the real HelpDesk application
and inspect realistic data. It is intentionally separate from
``app.commands.seed_qa_data`` (which targets a loopback-only isolated QA
database) so that neither command can ever silently target the other's
database:

* this command refuses loopback hosts and any database whose name starts with
  ``helpdesk_qa``;
* ``seed_qa_data`` refuses any non-loopback host, so it can never touch Neon.

Safety model (all must hold before a single row is written):

* ``HELPDESK_NEON_SEED_CONFIRM`` (or ``--confirm``) must equal the exact demo
  namespace **and** target identity token, e.g.
  ``HD-NEON-QA-20261018 @ ep-...neon.tech/neondb``;
* the configured ``DATABASE_URL`` host and database name must match the
  verified development target constants below;
* the environment must not be declared ``production``/``prod``;
* the attachment upload directory must live under ``/tmp``.

Everything it writes belongs to the demo namespace ``HD-NEON-QA-20261018`` and
uses deterministic uuid5 identifiers, so re-running adds nothing and duplicates
nothing. It never runs on application startup and never modifies the existing
Owner row, existing tickets, or any existing application record.

Usage (from ``backend/`` with the project environment active)::

    HELPDESK_NEON_SEED_CONFIRM='HD-NEON-QA-20261018 @ <host>/neondb' \\
    HELPDESK_NEON_UPLOAD_DIR=/tmp/helpdesk-neon-qa-uploads \\
    uv run python -m app.commands.seed_neon_demo

Add ``--verify-only`` to re-read and report the seeded namespace without
inserting anything.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import urllib.parse
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import func, or_, text
from sqlmodel import select

from app.core.config import settings
from app.core.database import async_session, engine
from app.enums.enums import NotificationType, Role, TicketPriority, TicketStatus
from app.models import (
    Attachment,
    Comment,
    Notification,
    Ticket,
    TicketHistory,
    User,
)
from app.services.tickets import TICKET_NUMBER_START

# --------------------------------------------------------------------------- #
# Namespace and target identity
# --------------------------------------------------------------------------- #

MARKER = "HD-NEON-QA-20261018"
CONFIRM_ENV = "HELPDESK_NEON_SEED_CONFIRM"

# The verified Neon *development* target. Changing these constants (a reviewed
# change) is required before this command can ever write anywhere else.
EXPECTED_HOST = "ep-proud-surf-b5oyh4qr-pooler.c-7.us-east-2.aws.neon.tech"
EXPECTED_DB = "neondb"
EXPECTED_TOKEN = f"{MARKER} @ {EXPECTED_HOST}/{EXPECTED_DB}"

QA_UPLOAD_DIR = "/tmp/helpdesk-neon-qa-uploads"

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, f"https://helpdesk.qa.local/neon/{MARKER}")

_BASE = datetime(2026, 10, 18, 6, 0, tzinfo=timezone.utc)


class SeedRefused(RuntimeError):
    """Raised for any condition that makes seeding unsafe."""


def _uid(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"{kind}:{key}")


def _at(minutes: int) -> datetime:
    return _BASE + timedelta(minutes=minutes)


def _parsed(url: str) -> urllib.parse.ParseResult:
    return urllib.parse.urlparse(url)


def redacted_target(url: str) -> str:
    """A secret-free ``host/database`` description of the configured target."""
    parsed = _parsed(url)
    host = parsed.hostname or "?"
    name = (parsed.path or "").lstrip("/") or "?"
    # Reveal only the leading label of the host, never credentials or the query
    # string (which can carry a password token).
    head = host.split(".")[0]
    short = f"{head[:6]}***.{'.'.join(host.split('.')[1:])}" if "." in host else "***"
    return f"{short}/{name}"


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #


def assert_confirm(confirm: str | None) -> None:
    if confirm != EXPECTED_TOKEN:
        raise SeedRefused(
            "An explicit confirmation is required. Set "
            f"{CONFIRM_ENV} (or --confirm) to exactly:\n    {EXPECTED_TOKEN}\n"
            "This proves the intended demo namespace and target database."
        )


def assert_not_production(environ: dict[str, str]) -> None:
    declared = (
        (
            environ.get("HELPDESK_ENVIRONMENT")
            or environ.get("APP_ENV")
            or environ.get("ENVIRONMENT")
            or ""
        )
        .strip()
        .lower()
    )
    if declared in {"production", "prod"}:
        raise SeedRefused("Refusing to seed: the environment is declared production.")


def assert_neon_target(url: str | None) -> None:
    if not url:
        raise SeedRefused("DATABASE_URL is not configured.")
    parsed = _parsed(url)
    host = parsed.hostname or ""
    name = (parsed.path or "").lstrip("/")

    if host in _LOOPBACK_HOSTS:
        raise SeedRefused(
            f"Refusing to seed a loopback database ({host!r}). This command "
            "targets the Neon development database only; use "
            "app.commands.seed_qa_data for the isolated QA database."
        )
    if name.startswith("helpdesk_qa"):
        raise SeedRefused(f"Refusing to seed a QA-named database ({name!r}).")
    if host != EXPECTED_HOST:
        raise SeedRefused(
            f"Unrecognized database host ({redacted_target(url)}). Expected the "
            "verified Neon development host. Refusing to write."
        )
    if name != EXPECTED_DB:
        raise SeedRefused(
            f"Unrecognized database name ({name!r}). Expected {EXPECTED_DB!r}."
        )


def assert_safe_upload_dir(upload_dir: str) -> Path:
    root = Path(upload_dir).resolve()
    tmp = Path("/tmp").resolve()
    if tmp not in root.parents and root != tmp:
        raise SeedRefused(
            f"Refusing to write QA attachments outside /tmp (got {root}). "
            f"Run with HELPDESK_NEON_UPLOAD_DIR={QA_UPLOAD_DIR}."
        )
    return root


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

_INACTIVE_CUSTOMERS = {33, 34, 35}


def qa_users() -> list[dict]:
    specs: list[dict] = []
    for i in range(1, 6):
        specs.append(
            dict(
                key=f"admin_{i:03d}",
                username=f"qa_admin_{i:03d}",
                email=f"qa.admin.{i:03d}@example.test",
                full_name=f"QA Admin {i:03d}",
                role=Role.ADMIN,
                is_active=True,
            )
        )
    for i in range(1, 11):
        specs.append(
            dict(
                key=f"agent_{i:03d}",
                username=f"qa_agent_{i:03d}",
                email=f"qa.agent.{i:03d}@example.test",
                full_name=f"QA Agent {i:03d}",
                role=Role.AGENT,
                is_active=True,
            )
        )
    for i in range(1, 36):
        specs.append(
            dict(
                key=f"customer_{i:03d}",
                username=f"qa_customer_{i:03d}",
                email=f"qa.customer.{i:03d}@example.test",
                full_name=f"QA Customer {i:03d}",
                role=Role.CUSTOMER,
                is_active=i not in _INACTIVE_CUSTOMERS,
            )
        )
    return specs


# Realistic ticket topics. Each entry is (subject, short description, long
# description). They are deliberately generic help-desk scenarios, never real
# employee or customer data.
_TOPICS: list[tuple[str, str, str]] = [
    (
        "Unable to sign in to the customer portal",
        "The portal rejects my login even after a password reset.",
        "Since this morning the customer portal returns an 'invalid credentials' "
        "message on every attempt, including immediately after completing the "
        "password reset flow. I have tried two different browsers and cleared "
        "cookies, and the behaviour is identical, so I believe the problem is on "
        "the account rather than my device.",
    ),
    (
        "Invoice export fails with a server error",
        "Exporting an invoice to PDF returns a server error.",
        "When I open an invoice and choose 'Export to PDF' the request spins for a "
        "few seconds and then fails with a generic server error. CSV export works "
        "fine, so it appears to be specific to the PDF pipeline. This is blocking "
        "our month-end reconciliation.",
    ),
    (
        "Password-reset email never arrives",
        "I never receive the password-reset email.",
        "I requested a password-reset link three times in the last hour and no "
        "email arrived, not even in the spam folder. A colleague on a different "
        "mail domain received theirs instantly, so the issue may affect my "
        "domain's delivery specifically.",
    ),
    (
        "Shared drive access denied after migration",
        "The 'Projects' shared drive returns access denied.",
        "After the weekend permission migration the shared 'Projects' drive "
        "returns access denied for my whole team. Personal drives still work, and "
        "we can read the drive from a machine that has not yet refreshed its "
        "group membership, which suggests the new group sync did not complete.",
    ),
    (
        "Printer on the third floor is offline",
        "The shared printer shows as offline.",
        "The shared printer on the third floor has shown as offline since early "
        "this morning. Everyone on the floor is affected and a power cycle at the "
        "wall socket did not help, so we may need someone to look at the print "
        "queue server.",
    ),
    (
        "VPN disconnects roughly every hour",
        "The VPN tunnel drops about once an hour.",
        "The remote-access VPN client drops the tunnel roughly once an hour and "
        "takes several minutes to reconnect, which interrupts file transfers and "
        "remote sessions. It started after the last client update was applied.",
    ),
    (
        "Duplicate charge on this month's invoice",
        "We were billed twice for the same subscription.",
        "Our account was charged twice for the same subscription in this month's "
        "invoice. The line items are identical and there is no upgrade or add-on "
        "that would explain the second charge, so we would like the duplicate "
        "refunded.",
    ),
    (
        "Email attachments larger than 2MB are rejected",
        "Larger email attachments bounce back.",
        "Any email with an attachment larger than about 2MB bounces back with a "
        "generic delivery-failure notice, while smaller attachments send normally. "
        "This affects the weekly reports we send to our customers.",
    ),
    (
        "Support status update request",
        "Please provide an update on my open request.",
        "Could you please provide an update on the status of my open request? It "
        "has been a few days since I reported it and I would like to know whether "
        "it is still being worked on and what the expected timeline is.",
    ),
    (
        "Feature request: dark mode",
        "A dark theme would help the late shift.",
        "It would help the team who work the late shift if the dashboard offered "
        "a dark theme. The current bright interface causes eye strain over long "
        "periods of monitoring, and a dark option would make the dashboard much "
        "more comfortable to use at night.",
    ),
    (
        "Production data sync is failing",
        "The nightly sync has failed three nights running.",
        "The nightly data sync has failed three nights in a row and the reporting "
        "dashboards are now stale. This is urgent because the numbers feed our "
        "operational reporting and leadership reviews the dashboard first thing "
        "each morning.",
    ),
    (
        "Laptop will not boot after the update",
        "The machine powers on but never reaches the login screen.",
        "After last night's maintenance the laptop powers on and shows the vendor "
        "logo, but it never reaches the login screen. Booting from a recovery "
        "image does let me reach a shell, so the hardware appears to be fine and "
        "the operating system update is the likely cause.",
    ),
]

_STATUS_CYCLE = [
    TicketStatus.OPEN,
    TicketStatus.IN_PROGRESS,
    TicketStatus.WAITING_ON_CUSTOMER,
    TicketStatus.RESOLVED,
    TicketStatus.CLOSED,
]
_PRIORITY_CYCLE = [
    TicketPriority.NORMAL,
    TicketPriority.HIGH,
    TicketPriority.LOW,
    TicketPriority.URGENT,
]


def ticket_specs() -> list[dict]:
    specs: list[dict] = []
    for i in range(1, 51):
        topic, short, long = _TOPICS[(i - 1) % len(_TOPICS)]
        customer_index = ((i - 1) % 35) + 1
        status = _STATUS_CYCLE[(i - 1) % len(_STATUS_CYCLE)]
        priority = _PRIORITY_CYCLE[(i - 1) % len(_PRIORITY_CYCLE)]
        # Leave every seventh ticket unassigned so the agent queue has work.
        unassigned = i % 7 == 0
        agent_index = ((i - 1) % 10) + 1
        use_long = i % 2 == 0
        specs.append(
            dict(
                key=f"ticket_{i:03d}",
                index=i,
                title=f"[{MARKER}] {topic}",
                description=(f"[{MARKER}] " + (long if use_long else short)),
                status=status,
                priority=priority,
                customer_key=f"customer_{customer_index:03d}",
                agent_key=None if unassigned else f"agent_{agent_index:03d}",
                at=i,
            )
        )
    return specs


_COMMENT_TEXTS = [
    "Hello, I am still unable to sign in and would like an account-access reset please.",
    "The invoice export is still failing for me; is there anything else I should try?",
    "Could you send me a support-status update when you have a moment?",
    "The password-reset link appears to have expired before I could use it.",
    "Confirming the problem is resolved on my side now, thank you for the help.",
    "I have attached the error text I see when the export fails.",
    "Thanks for looking into this; the workaround is working for now.",
    "The issue has started again this morning after briefly working yesterday.",
]
_INTERNAL_NOTES = [
    "Internal: reproduced on staging; escalating to the platform team.",
    "Internal: root cause appears to be a stale permission group after migration.",
    "Internal: finance has been asked to re-issue the affected invoices.",
    "Internal: customer account flagged for a manual access reset.",
]


def comment_specs(tickets: list[dict]) -> list[dict]:
    """Exactly 50 comments: two for the first 20 tickets, one for the next 10."""
    specs: list[dict] = []
    for spec in tickets:
        i = spec["index"]
        if i > 30:
            break
        text = _COMMENT_TEXTS[(i - 1) % len(_COMMENT_TEXTS)]
        specs.append(
            dict(
                key=f"comment_{i:03d}_a",
                ticket_key=spec["key"],
                author_key=spec["customer_key"],
                body=f"{text} [{MARKER}]",
                internal=False,
                at=spec["at"] + 100,
            )
        )
        if i <= 20:
            # Mix public agent replies with internal staff notes. Unassigned
            # tickets can only carry an internal note (staff-authored).
            make_internal = (i % 2 == 0) or (spec["agent_key"] is None)
            if make_internal:
                specs.append(
                    dict(
                        key=f"comment_{i:03d}_b",
                        ticket_key=spec["key"],
                        author_key=f"agent_{((i - 1) % 10) + 1:03d}",
                        body=(
                            _INTERNAL_NOTES[(i - 1) % len(_INTERNAL_NOTES)]
                            + f" [{MARKER}]"
                        ),
                        internal=True,
                        at=spec["at"] + 101,
                    )
                )
            else:
                specs.append(
                    dict(
                        key=f"comment_{i:03d}_b",
                        ticket_key=spec["key"],
                        author_key=spec["agent_key"],
                        body=(
                            "Thanks for the details - I am looking into this now "
                            f"and will update you shortly. [{MARKER}]"
                        ),
                        internal=False,
                        at=spec["at"] + 101,
                    )
                )
    assert len(specs) == 50, len(specs)
    return specs


# A 1x1 transparent PNG kept for reference; the Neon QA set uses text files only
# so every artifact is trivially safe to inspect.
_ATTACHMENT_FILES = [
    ("error-log.txt", "Portal error text captured by the customer.\n"),
    ("invoice-export.txt", "Steps to reproduce the invoice PDF export failure.\n"),
    ("password-reset-notes.txt", "Timeline of password-reset attempts.\n"),
    ("shared-drive-notes.txt", "Group membership before the migration.\n"),
    ("status-update.txt", "Customer status-update request details.\n"),
]


def attachment_specs(tickets: list[dict]) -> list[dict]:
    assigned = [spec for spec in tickets if spec["agent_key"]]
    specs: list[dict] = []
    for idx, (filename, body) in enumerate(_ATTACHMENT_FILES):
        spec = assigned[idx]
        specs.append(
            dict(
                key=f"attachment_{idx + 1:02d}",
                ticket_key=spec["key"],
                uploader_key=spec["customer_key"],
                filename=filename,
                content=(f"[{MARKER}] " + body + f"Marker: {MARKER}\n").encode("utf-8"),
                content_type="text/plain",
                at=spec["at"] + 200 + idx,
            )
        )
    return specs


def notification_specs(tickets: list[dict]) -> list[dict]:
    """Exactly 50 notifications across the four supported enum types."""
    assigned = [spec for spec in tickets if spec["agent_key"]]
    non_open = [spec for spec in tickets if spec["status"] != TicketStatus.OPEN]
    non_normal = [spec for spec in tickets if spec["priority"] != TicketPriority.NORMAL]

    chosen: list[tuple[dict, str, str, NotificationType, str, str]] = []
    # (ticket_spec, recipient_key, title, type, message, key)

    # Messages use a ``{number}`` placeholder replaced at insert time with the
    # real allocated ticket number (which is only known once rows are written).
    for spec in assigned[:10]:
        chosen.append(
            (
                spec,
                spec["agent_key"],
                f"Ticket assigned to you [{MARKER}]",
                NotificationType.TICKET_ASSIGNED,
                f"Ticket #{{number}} was assigned to you. [{MARKER}]",
                f"notif_assigned_{spec['index']:03d}",
            )
        )
    for spec in assigned[10:20]:
        chosen.append(
            (
                spec,
                spec["customer_key"],
                f"New comment on your ticket [{MARKER}]",
                NotificationType.NEW_COMMENT,
                f"A new comment was added to ticket #{{number}}. [{MARKER}]",
                f"notif_comment_{spec['index']:03d}",
            )
        )
    for spec in non_open[:20]:
        chosen.append(
            (
                spec,
                spec["customer_key"],
                f"Ticket status updated [{MARKER}]",
                NotificationType.STATUS_CHANGED,
                f"Ticket #{{number}} is now {spec['status'].value}. [{MARKER}]",
                f"notif_status_{spec['index']:03d}",
            )
        )
    for spec in non_normal[:10]:
        chosen.append(
            (
                spec,
                spec["customer_key"],
                f"Ticket priority updated [{MARKER}]",
                NotificationType.PRIORITY_CHANGED,
                f"Ticket #{{number}} priority is now {spec['priority'].value}. [{MARKER}]",
                f"notif_priority_{spec['index']:03d}",
            )
        )

    assert len(chosen) == 50, len(chosen)

    specs: list[dict] = []
    for idx, (spec, recipient_key, title, ntype, message, key) in enumerate(chosen):
        specs.append(
            dict(
                key=key,
                recipient_key=recipient_key,
                ticket_key=spec["key"],
                type=ntype,
                title=title[:180],
                message=message[:500],
                is_read=(idx % 3 == 0),
                at=spec["at"] + 300 + idx,
            )
        )
    return specs


def history_specs(tickets: list[dict]) -> list[dict]:
    """History consistent with each ticket's final state. Owner is never actor."""
    specs: list[dict] = []
    admin_key = "admin_001"
    for spec in tickets:
        i = spec["index"]
        actor_key = spec["agent_key"] or admin_key
        specs.append(
            dict(
                key=f"history_{i:03d}_created",
                ticket_key=spec["key"],
                actor_key=spec["customer_key"],
                event_type="TICKET_CREATED",
                old_value=None,
                new_value={"status": "OPEN"},
                at=spec["at"] + 10,
            )
        )
        if spec["agent_key"]:
            specs.append(
                dict(
                    key=f"history_{i:03d}_assigned",
                    ticket_key=spec["key"],
                    actor_key=admin_key,
                    event_type="TICKET_ASSIGNED",
                    old_value={"assignee_user_id": None},
                    new_value={"assignee_user_id": spec["agent_key"]},
                    at=spec["at"] + 11,
                )
            )

        path: list[tuple[str, str]] = []
        if spec["status"] == TicketStatus.IN_PROGRESS:
            path = [("OPEN", "IN_PROGRESS")]
        elif spec["status"] == TicketStatus.WAITING_ON_CUSTOMER:
            path = [("OPEN", "IN_PROGRESS"), ("IN_PROGRESS", "WAITING_ON_CUSTOMER")]
        elif spec["status"] == TicketStatus.RESOLVED:
            path = [("OPEN", "IN_PROGRESS"), ("IN_PROGRESS", "RESOLVED")]
        elif spec["status"] == TicketStatus.CLOSED:
            path = [("OPEN", "IN_PROGRESS"), ("IN_PROGRESS", "CLOSED")]
        for pos, (old, new) in enumerate(path):
            specs.append(
                dict(
                    key=f"history_{i:03d}_status_{pos}",
                    ticket_key=spec["key"],
                    actor_key=actor_key,
                    event_type="STATUS_CHANGED",
                    old_value={"status": old},
                    new_value={"status": new},
                    at=spec["at"] + 12 + pos,
                )
            )
        if spec["priority"] != TicketPriority.NORMAL:
            specs.append(
                dict(
                    key=f"history_{i:03d}_priority",
                    ticket_key=spec["key"],
                    actor_key=actor_key,
                    event_type="PRIORITY_CHANGED",
                    old_value={"priority": "NORMAL"},
                    new_value={"priority": spec["priority"].value},
                    at=spec["at"] + 15,
                )
            )
    return specs


# --------------------------------------------------------------------------- #
# Seeding
# --------------------------------------------------------------------------- #


class Counts:
    def __init__(self) -> None:
        self.inserted = 0
        self.reused = 0
        self.conflicts = 0
        self.failed = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "inserted": self.inserted,
            "reused": self.reused,
            "skipped_conflicts": self.conflicts,
            "failed": self.failed,
        }


async def _seed_users(session) -> tuple[dict[str, User], Counts, list[str]]:
    counts = Counts()
    users: dict[str, User] = {}
    collisions: list[str] = []
    specs = qa_users()
    usernames = [spec["username"] for spec in specs]
    emails = [spec["email"] for spec in specs]
    # One round-trip: fetch any user that collides on username or email.
    existing_rows = (
        await session.exec(
            select(User).where(
                or_(User.username.in_(usernames), User.email.in_(emails))
            )
        )
    ).all()
    by_username = {row.username: row for row in existing_rows}
    by_email = {row.email: row for row in existing_rows}

    for spec in specs:
        expected_id = _uid("user", spec["key"])
        existing = by_username.get(spec["username"]) or by_email.get(spec["email"])
        if existing is not None:
            if existing.id == expected_id:
                counts.reused += 1
                users[spec["key"]] = existing
            else:
                counts.conflicts += 1
                collisions.append(
                    f"user {spec['username']} / {spec['email']} exists with a "
                    f"different id ({existing.id}); refusing to overwrite"
                )
            continue
        # The primary key is deterministic, so no flush is required to use it.
        user = User(
            id=expected_id,
            clerk_id=None,
            full_name=spec["full_name"],
            username=spec["username"],
            email=spec["email"],
            password_hash=None,
            role=spec["role"],
            is_active=spec["is_active"],
            created_at=_at(0),
            updated_at=_at(0),
        )
        session.add(user)
        counts.inserted += 1
        users[spec["key"]] = user

    await session.flush()
    return users, counts, collisions


async def _seed_tickets(
    session, users: dict[str, User], tickets: list[dict]
) -> tuple[dict[str, Ticket], Counts, list[str]]:
    counts = Counts()
    result: dict[str, Ticket] = {}
    collisions: list[str] = []
    expected_ids = [_uid("ticket", spec["key"]) for spec in tickets]
    existing_rows = (
        await session.exec(select(Ticket).where(Ticket.id.in_(expected_ids)))
    ).all()
    existing_by_id = {row.id: row for row in existing_rows}

    # Allocate ticket numbers from a single read of the current maximum. The
    # maximum is by definition higher than every existing number, so starting
    # at ``max + 1`` and incrementing never collides with an existing ticket.
    # The advisory lock taken by the caller serialises this against writers.
    max_row = (await session.exec(select(func.max(Ticket.ticket_number)))).one()
    next_number = (max_row or TICKET_NUMBER_START) + 1

    for spec in tickets:
        ticket_id = _uid("ticket", spec["key"])
        if ticket_id in existing_by_id:
            counts.reused += 1
            result[spec["key"]] = existing_by_id[ticket_id]
            continue
        number = next_number
        next_number += 1
        agent = users.get(spec["agent_key"]) if spec["agent_key"] else None
        ticket = Ticket(
            id=ticket_id,
            ticket_number=number,
            title=spec["title"],
            description=spec["description"],
            status=spec["status"],
            priority=spec["priority"],
            created_by_user_id=users[spec["customer_key"]].id,
            assignee_user_id=agent.id if agent else None,
            created_at=_at(spec["at"]),
            updated_at=_at(spec["at"]),
            resolved_at=(
                _at(spec["at"] + 12)
                if spec["status"] == TicketStatus.RESOLVED
                else None
            ),
        )
        session.add(ticket)
        counts.inserted += 1
        result[spec["key"]] = ticket
    await session.flush()
    return result, counts, collisions


async def _seed_comments(session, users, tickets_map) -> tuple[Counts, list[str]]:
    counts = Counts()
    collisions: list[str] = []
    specs = comment_specs(ticket_specs())
    expected_ids = [_uid("comment", spec["key"]) for spec in specs]
    existing = set(
        (
            await session.exec(select(Comment.id).where(Comment.id.in_(expected_ids)))
        ).all()
    )
    for spec in specs:
        expected_id = _uid("comment", spec["key"])
        if expected_id in existing:
            counts.reused += 1
            continue
        session.add(
            Comment(
                id=expected_id,
                ticket_id=tickets_map[spec["ticket_key"]].id,
                author_user_id=users[spec["author_key"]].id,
                body=spec["body"],
                is_internal=spec["internal"],
                created_at=_at(spec["at"]),
            )
        )
        counts.inserted += 1
    return counts, collisions


async def _seed_history(session, users, tickets_map) -> Counts:
    counts = Counts()
    specs = history_specs(ticket_specs())
    expected_ids = [_uid("history", spec["key"]) for spec in specs]
    existing = set(
        (
            await session.exec(
                select(TicketHistory.id).where(TicketHistory.id.in_(expected_ids))
            )
        ).all()
    )
    for spec in specs:
        expected_id = _uid("history", spec["key"])
        if expected_id in existing:
            counts.reused += 1
            continue
        old_value = spec["old_value"]
        new_value = spec["new_value"]
        if isinstance(new_value, dict) and spec["event_type"] == "TICKET_ASSIGNED":
            new_value = {
                "assignee_user_id": str(users[spec["new_value"]["assignee_user_id"]].id)
            }
        session.add(
            TicketHistory(
                id=expected_id,
                ticket_id=tickets_map[spec["ticket_key"]].id,
                actor_user_id=users[spec["actor_key"]].id,
                event_type=spec["event_type"],
                old_value=old_value,
                new_value=new_value,
                created_at=_at(spec["at"]),
            )
        )
        counts.inserted += 1
    return counts


async def _seed_notifications(session, users, tickets_map) -> Counts:
    counts = Counts()
    specs = notification_specs(ticket_specs())
    expected_ids = [_uid("notification", spec["key"]) for spec in specs]
    existing = set(
        (
            await session.exec(
                select(Notification.id).where(Notification.id.in_(expected_ids))
            )
        ).all()
    )
    for spec in specs:
        expected_id = _uid("notification", spec["key"])
        if expected_id in existing:
            counts.reused += 1
            continue
        session.add(
            Notification(
                id=expected_id,
                recipient_user_id=users[spec["recipient_key"]].id,
                related_ticket_id=tickets_map[spec["ticket_key"]].id,
                type=spec["type"],
                title=spec["title"],
                message=spec["message"].replace(
                    "{number}",
                    str(tickets_map[spec["ticket_key"]].ticket_number),
                )[:500],
                is_read=spec["is_read"],
                created_at=_at(spec["at"]),
            )
        )
        counts.inserted += 1
    return counts


async def _seed_attachments(
    session, users, tickets_map, upload_root: Path
) -> tuple[Counts, list[Path], list[str]]:
    counts = Counts()
    written: list[Path] = []
    collisions: list[str] = []
    upload_root.mkdir(parents=True, exist_ok=True)
    specs = attachment_specs(ticket_specs())
    expected_ids = [_uid("attachment", spec["key"]) for spec in specs]
    existing = set(
        (
            await session.exec(
                select(Attachment.id).where(Attachment.id.in_(expected_ids))
            )
        ).all()
    )
    for spec in specs:
        expected_id = _uid("attachment", spec["key"])
        storage_key = f"qa-neon-{expected_id.hex[:12]}-{spec['filename']}"
        destination = upload_root / storage_key
        if expected_id in existing:
            counts.reused += 1
            # Repair a missing file so a download always succeeds.
            if not destination.exists():
                destination.write_bytes(spec["content"])
                written.append(destination)
            continue
        session.add(
            Attachment(
                id=expected_id,
                ticket_id=tickets_map[spec["ticket_key"]].id,
                uploaded_by_user_id=users[spec["uploader_key"]].id,
                original_filename=spec["filename"],
                storage_key=storage_key,
                content_type=spec["content_type"],
                size_bytes=len(spec["content"]),
                created_at=_at(spec["at"]),
            )
        )
        destination.write_bytes(spec["content"])
        written.append(destination)
        counts.inserted += 1
    return counts, written, collisions


async def _owner_row(session) -> dict | None:
    owner = (await session.exec(select(User).where(User.role == Role.OWNER))).first()
    if owner is None:
        return None
    return {
        "id": str(owner.id),
        "clerk_id": owner.clerk_id,
        "full_name": owner.full_name,
        "username": owner.username,
        "email": owner.email,
        "password_hash": owner.password_hash,
        "role": owner.role.value,
        "is_active": owner.is_active,
        "created_at": owner.created_at.isoformat(),
        "updated_at": owner.updated_at.isoformat(),
    }


async def seed(upload_root: Path) -> dict:
    tickets = ticket_specs()
    notifications = notification_specs(tickets)
    comments = comment_specs(tickets)
    history = history_specs(tickets)
    attachments = attachment_specs(tickets)

    created_files: list[Path] = []
    async with async_session() as session:
        owner_before = await _owner_row(session)
        if owner_before is None:
            raise SeedRefused(
                "No OWNER row found in the target database; refusing to seed."
            )

        # Serialize ticket-number allocation against concurrent app writers.
        if engine.dialect.name == "postgresql":
            await session.exec(
                text("SELECT pg_advisory_xact_lock(:key)"),
                params={"key": 20261018},
            )

        try:
            users, users_counts, user_collisions = await _seed_users(session)
            needed = {s["customer_key"] for s in tickets}
            needed |= {s["agent_key"] for s in tickets if s["agent_key"]}
            needed |= {"admin_001"}
            missing = [k for k in needed if k not in users]
            if missing:
                raise SeedRefused(
                    "Refusing to seed: required QA users could not be created "
                    f"({len(missing)} unresolved). Conflicts: {user_collisions}"
                )

            tickets_map, ticket_counts, ticket_collisions = await _seed_tickets(
                session, users, tickets
            )
            comment_counts, comment_collisions = await _seed_comments(
                session, users, tickets_map
            )
            history_counts = await _seed_history(session, users, tickets_map)
            notif_counts = await _seed_notifications(session, users, tickets_map)
            attach_counts, created_files, attach_collisions = await _seed_attachments(
                session, users, tickets_map, upload_root
            )

            owner_after = await _owner_row(session)
            if owner_after != owner_before:
                raise SeedRefused(
                    "Owner row changed unexpectedly during seeding; rolling back."
                )

            await session.commit()
        except Exception:
            await session.rollback()
            for path in created_files:
                path.unlink(missing_ok=True)
            raise

    return {
        "marker": MARKER,
        "users": users_counts.as_dict(),
        "tickets": ticket_counts.as_dict(),
        "comments": comment_counts.as_dict(),
        "history": history_counts.as_dict(),
        "notifications": notif_counts.as_dict(),
        "attachments": attach_counts.as_dict(),
        "collisions": user_collisions + ticket_collisions + comment_collisions,
        "owner_before": owner_before,
        "expected": {
            "users": len(qa_users()),
            "tickets": len(tickets),
            "comments": len(comments),
            "history": len(history),
            "notifications": len(notifications),
            "attachments": len(attachments),
        },
    }


async def read_manifest() -> dict:
    """Read back the full seeded namespace from PostgreSQL (source of truth)."""
    users = qa_users()
    tickets = ticket_specs()
    manifest: dict = {
        "marker": MARKER,
        "users": [],
        "tickets": [],
        "comments": [],
        "notifications": [],
        "history": [],
        "attachments": [],
    }

    async with async_session() as session:
        owner = await _owner_row(session)
        manifest["owner_row_hash_source"] = owner

        user_rows = (
            await session.exec(select(User).where(User.username.startswith("qa_")))
        ).all()
        # Only include this namespace's deterministic ids.
        expected_user_ids = {str(_uid("user", s["key"])): s for s in users}
        for row in user_rows:
            if str(row.id) in expected_user_ids:
                manifest["users"].append(
                    {
                        "id": str(row.id),
                        "username": row.username,
                        "email": row.email,
                        "role": row.role.value,
                        "is_active": row.is_active,
                        "clerk_id": row.clerk_id,
                    }
                )
        manifest["users"].sort(key=lambda r: r["username"])

        ticket_rows = (
            await session.exec(select(Ticket).where(Ticket.title.like(f"%{MARKER}%")))
        ).all()
        # Build id -> username map for readable output.
        id_to_username = {r["id"]: r["username"] for r in manifest["users"]}
        for row in ticket_rows:
            manifest["tickets"].append(
                {
                    "id": str(row.id),
                    "ticket_number": row.ticket_number,
                    "title": row.title,
                    "status": row.status.value,
                    "priority": row.priority.value,
                    "created_by": id_to_username.get(str(row.created_by_user_id)),
                    "assignee": id_to_username.get(str(row.assignee_user_id))
                    if row.assignee_user_id
                    else None,
                }
            )
        manifest["tickets"].sort(key=lambda r: r["ticket_number"] or 0)

        expected_comment_ids = {
            str(_uid("comment", s["key"])) for s in comment_specs(tickets)
        }
        comment_rows = (
            await session.exec(select(Comment).where(Comment.body.like(f"%{MARKER}%")))
        ).all()
        for row in comment_rows:
            if str(row.id) in expected_comment_ids:
                manifest["comments"].append(
                    {
                        "id": str(row.id),
                        "ticket_number": next(
                            (
                                t["ticket_number"]
                                for t in manifest["tickets"]
                                if t["id"] == str(row.ticket_id)
                            ),
                            None,
                        ),
                        "author": id_to_username.get(str(row.author_user_id)),
                        "is_internal": row.is_internal,
                        "body": row.body,
                    }
                )

        expected_notif_ids = {
            str(_uid("notification", s["key"])) for s in notification_specs(tickets)
        }
        notif_rows = (
            await session.exec(
                select(Notification).where(Notification.title.like(f"%{MARKER}%"))
            )
        ).all()
        for row in notif_rows:
            if str(row.id) in expected_notif_ids:
                manifest["notifications"].append(
                    {
                        "id": str(row.id),
                        "recipient": id_to_username.get(str(row.recipient_user_id)),
                        "type": row.type.value,
                        "title": row.title,
                        "message": row.message,
                        "is_read": row.is_read,
                    }
                )

        expected_hist_ids = {
            str(_uid("history", s["key"])) for s in history_specs(tickets)
        }
        hist_rows = (
            await session.exec(
                select(TicketHistory).where(
                    TicketHistory.id.in_([uuid.UUID(x) for x in expected_hist_ids])
                )
            )
        ).all()
        for row in hist_rows:
            manifest["history"].append(
                {
                    "id": str(row.id),
                    "ticket_number": next(
                        (
                            t["ticket_number"]
                            for t in manifest["tickets"]
                            if t["id"] == str(row.ticket_id)
                        ),
                        None,
                    ),
                    "actor": id_to_username.get(str(row.actor_user_id)),
                    "event_type": row.event_type,
                    "old_value": row.old_value,
                    "new_value": row.new_value,
                }
            )

        expected_att_ids = {
            str(_uid("attachment", s["key"])) for s in attachment_specs(tickets)
        }
        att_rows = (
            await session.exec(
                select(Attachment).where(
                    Attachment.id.in_([uuid.UUID(x) for x in expected_att_ids])
                )
            )
        ).all()
        for row in att_rows:
            manifest["attachments"].append(
                {
                    "id": str(row.id),
                    "ticket_number": next(
                        (
                            t["ticket_number"]
                            for t in manifest["tickets"]
                            if t["id"] == str(row.ticket_id)
                        ),
                        None,
                    ),
                    "uploaded_by": id_to_username.get(str(row.uploaded_by_user_id)),
                    "original_filename": row.original_filename,
                    "storage_key": row.storage_key,
                    "content_type": row.content_type,
                    "size_bytes": row.size_bytes,
                    "path": str(
                        (Path(settings.UPLOAD_DIR).resolve() / row.storage_key)
                    ),
                }
            )
    return manifest


# --------------------------------------------------------------------------- #
# Entry points
# --------------------------------------------------------------------------- #


def _print_counts(result: dict) -> None:
    print(f"Neon demo seed ({result['marker']})")
    for kind in (
        "users",
        "tickets",
        "comments",
        "history",
        "notifications",
        "attachments",
    ):
        c = result[kind]
        exp = result["expected"][kind]
        print(
            f"  {kind:<14}: inserted={c['inserted']:<3} reused={c['reused']:<3} "
            f"conflicts={c['skipped_conflicts']:<2} failed={c['failed']:<2} "
            f"(expected {exp})"
        )
    if result["collisions"]:
        print("  collisions:")
        for line in result["collisions"]:
            print(f"    - {line}")


async def _verify(result: dict) -> bool:
    ok = True
    manifest = await read_manifest()
    expect = result["expected"]
    for kind in ("users", "tickets", "comments", "notifications", "attachments"):
        got = len(manifest[kind])
        if got < expect[kind]:
            ok = False
            print(f"  VERIFY FAIL: {kind} present={got} expected={expect[kind]}")
        else:
            print(f"  VERIFY ok  : {kind} present={got}")
    hist = len(manifest["history"])
    if hist < expect["history"]:
        ok = False
        print(f"  VERIFY FAIL: history present={hist} expected={expect['history']}")
    else:
        print(f"  VERIFY ok  : history present={hist}")
    return ok


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm", default=os.environ.get(CONFIRM_ENV))
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument(
        "--manifest",
        default=os.environ.get(
            "HELPDESK_NEON_SEED_MANIFEST",
            "/tmp/opencode/helpdesk-neon-qa-manifest.json",
        ),
    )
    args = parser.parse_args(argv)

    try:
        assert_not_production(dict(os.environ))
        assert_neon_target(settings.DATABASE_URL)
        assert_confirm(args.confirm)
        upload_root = assert_safe_upload_dir(settings.UPLOAD_DIR)
    except SeedRefused as exc:
        print(f"Neon demo seed refused: {exc}", file=sys.stderr)
        return 2

    print("Target verified (redacted):")
    print(f"  database    : {redacted_target(settings.DATABASE_URL)}")
    print(f"  upload dir  : {upload_root}")
    print(f"  namespace   : {MARKER}")

    if args.verify_only:
        result = {
            "marker": MARKER,
            "expected": {
                "users": len(qa_users()),
                "tickets": len(ticket_specs()),
                "comments": len(comment_specs(ticket_specs())),
                "history": len(history_specs(ticket_specs())),
                "notifications": len(notification_specs(ticket_specs())),
                "attachments": len(attachment_specs(ticket_specs())),
            },
        }
        ok = await _verify(result)
        return 0 if ok else 1

    result = await seed(upload_root)
    _print_counts(result)
    print("Verifying from PostgreSQL ...")
    ok = await _verify(result)

    manifest = await read_manifest()
    manifest["seed_result"] = {
        k: result[k]
        for k in (
            "users",
            "tickets",
            "comments",
            "history",
            "notifications",
            "attachments",
            "expected",
            "collisions",
        )
    }
    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str))
    os.chmod(manifest_path, 0o600)
    print(f"Manifest written: {manifest_path}")
    return 0 if ok else 1


def main() -> int:
    return asyncio.run(_main(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
