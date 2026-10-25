"""Deterministic QA seed data for manual and automated inspection.

Usage, from the ``backend/`` directory with the project environment active::

    HELPDESK_QA_SEED=1 \\
    DATABASE_URL='postgresql+psycopg://qa_test:qa_test_only@127.0.0.1:55439/helpdesk_qa' \\
    UPLOAD_DIR=/tmp/helpdesk-qa-uploads \\
    uv run python -m app.commands.seed_qa_data

This command exists only to populate an *isolated* QA database with stable,
reproducible fixtures for visual review and authorization testing. It is
deliberately hard to point at the wrong place:

* it refuses to run unless ``HELPDESK_QA_SEED=1`` is set explicitly,
* it refuses any database whose host is not loopback,
* it refuses any database whose name is not a recognised QA database,
* it refuses to write attachments outside ``/tmp``,
* it never runs on application startup (nothing imports it),
* it is idempotent: every record uses a deterministic primary key (the ticket
  fixtures additionally keep stable ticket numbers when those numbers are
  free; on a database that mixes in app-created tickets a colliding fixture is
  created under a fresh number instead of overwriting or adopting the foreign
  row), so re-running adds nothing and duplicates nothing.

It does not create real credentials, session tokens, or copy real customer
messages. Personas use reserved ``.test`` email domains. The one exception is
the QA Owner: if ``INITIAL_ADMIN_EMAIL`` is configured, that identity is seeded
as the single local OWNER so the real Clerk account can link to it through the
application's normal verified-primary-email flow. The row carries no Clerk id
and no password: Clerk still has to verify the email at sign-in. See
``app.commands.bootstrap_owner`` for the equivalent production flow.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import urllib.parse
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func
from sqlmodel import select

from app.core.config import settings
from app.core.database import async_session
from app.enums.enums import (
    AttachmentScanStatus,
    EscalationCategory,
    EscalationStatus,
    NotificationType,
    Role,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)
from app.models import (
    AccountManagementRequest,
    AccountRequestEvent,
    Attachment,
    Comment,
    Notification,
    StaffConversation,
    StaffMessage,
    Ticket,
    TicketHistory,
    User,
)
from app.services.tickets import TICKET_NUMBER_START

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Safety guards
# --------------------------------------------------------------------------- #

SEED_ENV_FLAG = "HELPDESK_QA_SEED"
_ALLOWED_DB_PREFIXES = ("helpdesk_qa",)
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


class SeedRefused(RuntimeError):
    """Raised for any condition that makes seeding unsafe."""


def _parsed(url: str) -> urllib.parse.ParseResult:
    # The SQLAlchemy driver suffix (``+psycopg``) is part of the scheme; urlparse
    # still exposes hostname/port/path correctly.
    return urllib.parse.urlparse(url)


def assert_safe_target(url: str | None) -> None:
    """Refuse anything that is not the isolated loopback QA database."""
    if not url:
        raise SeedRefused("DATABASE_URL is not configured.")
    parsed = _parsed(url)
    host = parsed.hostname
    name = (parsed.path or "").lstrip("/")
    if host not in _LOOPBACK_HOSTS:
        raise SeedRefused(
            f"Refusing to seed a non-loopback database host ({host!r}). "
            "This command only runs against a local QA database."
        )
    if not any(name.startswith(prefix) for prefix in _ALLOWED_DB_PREFIXES):
        raise SeedRefused(
            f"Refusing to seed an unrecognised database name ({name!r}). "
            f"Expected a name starting with one of {_ALLOWED_DB_PREFIXES}."
        )


def assert_seed_enabled(environ: dict[str, str]) -> None:
    if environ.get(SEED_ENV_FLAG) != "1":
        raise SeedRefused(
            f"{SEED_ENV_FLAG}=1 is required. This is a deliberate QA-only "
            "command and never runs automatically."
        )


def assert_safe_upload_dir(upload_dir: str) -> Path:
    root = Path(upload_dir).resolve()
    tmp = Path("/tmp").resolve()
    if tmp not in root.parents and root != tmp:
        raise SeedRefused(
            f"Refusing to write QA attachments outside /tmp (got {root}). "
            "Set UPLOAD_DIR=/tmp/helpdesk-qa-uploads for the seed run."
        )
    return root


# --------------------------------------------------------------------------- #
# Deterministic identifiers
# --------------------------------------------------------------------------- #

_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://helpdesk.qa.local/seed")


def _uid(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"{kind}:{key}")


# A fixed base timestamp keeps ordering and history stable across runs.
_BASE = datetime(2026, 1, 5, 9, 0, tzinfo=UTC)


def _at(minutes: int) -> datetime:
    return _BASE + timedelta(minutes=minutes)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #

OWNER_PLACEHOLDER_EMAIL = "qa.owner@example.test"


def owner_email() -> str:
    """The QA Owner email: the configured identity when available."""
    return settings.initial_admin_email or OWNER_PLACEHOLDER_EMAIL


def personas() -> list[dict]:
    return [
        dict(
            key="owner",
            email=owner_email(),
            username="qa_owner",
            full_name="QA Owner",
            role=Role.OWNER,
            is_active=True,
            clerk_id=None,
        ),
        dict(
            key="admin",
            email="qa.admin@example.test",
            username="qa_admin",
            full_name="QA Administrator",
            role=Role.ADMIN,
            is_active=True,
            clerk_id="test_qa_admin",
        ),
        dict(
            key="agent_aria",
            email="qa.agent.aria@example.test",
            username="qa_agent_aria",
            full_name="QA Agent Aria",
            role=Role.AGENT,
            is_active=True,
            clerk_id="test_qa_agent_aria",
        ),
        dict(
            key="agent_ben",
            email="qa.agent.ben@example.test",
            username="qa_agent_ben",
            full_name="QA Agent Ben",
            role=Role.AGENT,
            is_active=True,
            clerk_id="test_qa_agent_ben",
        ),
        dict(
            key="customer_alex",
            email="qa.customer.alex@example.test",
            username="qa_customer_alex",
            full_name="QA Customer Alex",
            role=Role.CUSTOMER,
            is_active=True,
            clerk_id="test_qa_customer_alex",
        ),
        dict(
            key="customer_jamie",
            email="qa.customer.jamie@example.test",
            username="qa_customer_jamie",
            full_name="QA Customer Jamie",
            role=Role.CUSTOMER,
            is_active=True,
            clerk_id="test_qa_customer_jamie",
        ),
        dict(
            key="inactive",
            email="qa.inactive@example.test",
            username="qa_inactive",
            full_name="QA Inactive Customer",
            role=Role.CUSTOMER,
            is_active=False,
            clerk_id="test_qa_inactive",
        ),
    ]


def tickets() -> list[dict]:
    n = TICKET_NUMBER_START
    return [
        dict(
            key="open_unassigned",
            number=n + 1,
            title="Cannot log in to the customer portal",
            description=(
                "Since this morning the portal returns 'invalid credentials' even "
                "after resetting my password."
            ),
            status=TicketStatus.OPEN,
            priority=TicketPriority.NORMAL,
            category=TicketCategory.ACCOUNT_ACCESS,
            owner="customer_alex",
            assignee=None,
            at=1,
        ),
        dict(
            key="open_assigned",
            number=n + 2,
            title="Printer on the 3rd floor is offline",
            description="The shared printer shows 'offline' for everyone on the floor.",
            status=TicketStatus.OPEN,
            priority=TicketPriority.HIGH,
            category=TicketCategory.OUTAGE,
            owner="customer_alex",
            assignee="agent_aria",
            at=2,
        ),
        dict(
            key="in_progress",
            number=n + 3,
            title="Invoice PDF is missing the tax line",
            description="Downloaded invoices omit the VAT line for EU customers.",
            status=TicketStatus.IN_PROGRESS,
            priority=TicketPriority.NORMAL,
            category=TicketCategory.BILLING,
            owner="customer_alex",
            assignee="agent_aria",
            at=3,
        ),
        dict(
            key="waiting_customer",
            number=n + 4,
            title="Please confirm the new billing address",
            description="We need written confirmation before the next invoice run.",
            status=TicketStatus.WAITING_ON_CUSTOMER,
            priority=TicketPriority.NORMAL,
            category=TicketCategory.BILLING,
            owner="customer_alex",
            assignee="agent_aria",
            at=4,
        ),
        dict(
            key="resolved",
            number=n + 5,
            title="VPN disconnects every hour",
            description="The corporate VPN drops the tunnel roughly hourly.",
            status=TicketStatus.RESOLVED,
            priority=TicketPriority.HIGH,
            category=TicketCategory.TECHNICAL,
            owner="customer_alex",
            assignee="agent_aria",
            at=5,
            resolved=True,
        ),
        dict(
            key="closed",
            number=n + 6,
            title="Duplicate charge on the August invoice",
            description="August was billed twice for the same subscription.",
            status=TicketStatus.CLOSED,
            priority=TicketPriority.NORMAL,
            category=TicketCategory.BILLING,
            owner="customer_alex",
            assignee="agent_aria",
            at=6,
        ),
        dict(
            key="urgent",
            number=n + 7,
            title="URGENT: production data sync is failing",
            description="Nightly sync has failed three nights in a row; dashboards are stale.",
            status=TicketStatus.OPEN,
            priority=TicketPriority.URGENT,
            category=TicketCategory.OUTAGE,
            owner="customer_jamie",
            assignee=None,
            at=7,
        ),
        dict(
            key="low_jamie",
            number=n + 8,
            title="Feature request: dark mode in the dashboard",
            description="A dark theme would reduce eye strain for the late shift.",
            status=TicketStatus.OPEN,
            priority=TicketPriority.LOW,
            category=TicketCategory.OTHER,
            owner="customer_jamie",
            assignee=None,
            at=8,
        ),
        dict(
            key="claim_candidate",
            number=n + 9,
            title="Laptop will not boot after last night's update",
            description="The machine powers on but never reaches the login screen.",
            status=TicketStatus.OPEN,
            priority=TicketPriority.NORMAL,
            category=TicketCategory.TECHNICAL,
            owner="customer_alex",
            assignee=None,
            at=9,
        ),
        dict(
            key="ben_in_progress",
            number=n + 10,
            title="Email attachments above 2MB are rejected",
            description="Larger PDFs bounce back with a generic delivery failure.",
            status=TicketStatus.IN_PROGRESS,
            priority=TicketPriority.NORMAL,
            category=TicketCategory.TECHNICAL,
            owner="customer_jamie",
            assignee="agent_ben",
            at=10,
        ),
        dict(
            key="ben_waiting",
            number=n + 11,
            title="Refund request for a duplicated order",
            description="Order #5521 was charged twice; please refund the duplicate.",
            status=TicketStatus.WAITING_ON_CUSTOMER,
            priority=TicketPriority.HIGH,
            category=TicketCategory.BILLING,
            owner="customer_jamie",
            assignee="agent_ben",
            at=11,
        ),
        dict(
            key="rich",
            number=n + 12,
            title="Access to the shared drive is denied",
            description=(
                "The 'Projects' shared drive returns access denied since the "
                "permission migration."
            ),
            status=TicketStatus.OPEN,
            priority=TicketPriority.HIGH,
            category=TicketCategory.ACCOUNT_ACCESS,
            owner="customer_alex",
            assignee="agent_aria",
            at=12,
        ),
    ]


def comments() -> list[dict]:
    return [
        dict(
            key="c_printer_public_agent",
            ticket="open_assigned",
            author="agent_aria",
            body="Thanks for the report - I have asked facilities to power-cycle it.",
            internal=False,
            at=20,
        ),
        dict(
            key="c_printer_public_customer",
            ticket="open_assigned",
            author="customer_alex",
            body="Any update? The whole floor is blocked.",
            internal=False,
            at=21,
        ),
        dict(
            key="c_invoice_public_customer",
            ticket="in_progress",
            author="customer_alex",
            body="This affects every invoice we export.",
            internal=False,
            at=22,
        ),
        dict(
            key="c_invoice_internal_agent",
            ticket="in_progress",
            author="agent_aria",
            body="Internal: reproduced on staging; root cause is the VAT template.",
            internal=True,
            at=23,
        ),
        dict(
            key="c_invoice_internal_admin",
            ticket="in_progress",
            author="admin",
            body="Internal: finance will re-issue the affected invoices once fixed.",
            internal=True,
            at=24,
        ),
        dict(
            key="c_waiting_public_agent",
            ticket="waiting_customer",
            author="agent_aria",
            body="Could you confirm the full address in writing so we can proceed?",
            internal=False,
            at=25,
        ),
        dict(
            key="c_vpn_public_agent",
            ticket="resolved",
            author="agent_aria",
            body="We pushed a client update; please reconnect and confirm.",
            internal=False,
            at=26,
        ),
        dict(
            key="c_closed_public_customer",
            ticket="closed",
            author="customer_alex",
            body="The refund arrived - thank you.",
            internal=False,
            at=27,
        ),
        dict(
            key="c_urgent_public_customer",
            ticket="urgent",
            author="customer_jamie",
            body="This is blocking our end-of-month reporting.",
            internal=False,
            at=28,
        ),
        dict(
            key="c_rich_public_customer",
            ticket="rich",
            author="customer_alex",
            body="Reproduced from a second machine as well.",
            internal=False,
            at=29,
        ),
        dict(
            key="c_rich_public_agent",
            ticket="rich",
            author="agent_aria",
            body="I can see the drive mapping; checking the group membership now.",
            internal=False,
            at=30,
        ),
        dict(
            key="c_rich_internal_agent",
            ticket="rich",
            author="agent_aria",
            body="Internal: the user is missing the 'projects-rw' group after migration.",
            internal=True,
            at=31,
        ),
        dict(
            key="c_rich_internal_admin",
            ticket="rich",
            author="admin",
            body="Internal: re-run the group sync before the next batch.",
            internal=True,
            at=32,
        ),
    ]


def history_events() -> list[dict]:
    return [
        dict(
            key="h_printer_created",
            ticket="open_assigned",
            actor="customer_alex",
            event_type="TICKET_CREATED",
            old_value=None,
            new_value={"status": "OPEN"},
            at=2,
        ),
        dict(
            key="h_printer_assigned",
            ticket="open_assigned",
            actor="admin",
            event_type="TICKET_ASSIGNED",
            old_value={"assignee_user_id": None},
            new_value={"assignee_user_id": "agent_aria"},
            at=13,
        ),
        dict(
            key="h_invoice_created",
            ticket="in_progress",
            actor="customer_alex",
            event_type="TICKET_CREATED",
            old_value=None,
            new_value={"status": "OPEN"},
            at=3,
        ),
        dict(
            key="h_invoice_status",
            ticket="in_progress",
            actor="agent_aria",
            event_type="STATUS_CHANGED",
            old_value={"status": "OPEN"},
            new_value={"status": "IN_PROGRESS"},
            at=14,
        ),
        dict(
            key="h_invoice_priority",
            ticket="in_progress",
            actor="agent_aria",
            event_type="PRIORITY_CHANGED",
            old_value={"priority": "LOW"},
            new_value={"priority": "NORMAL"},
            at=15,
        ),
        dict(
            key="h_vpn_created",
            ticket="resolved",
            actor="customer_alex",
            event_type="TICKET_CREATED",
            old_value=None,
            new_value={"status": "OPEN"},
            at=5,
        ),
        dict(
            key="h_vpn_status",
            ticket="resolved",
            actor="agent_aria",
            event_type="STATUS_CHANGED",
            old_value={"status": "IN_PROGRESS"},
            new_value={"status": "RESOLVED"},
            at=16,
        ),
        dict(
            key="h_closed_status",
            ticket="closed",
            actor="admin",
            event_type="STATUS_CHANGED",
            old_value={"status": "RESOLVED"},
            new_value={"status": "CLOSED"},
            at=17,
        ),
        dict(
            key="h_rich_created",
            ticket="rich",
            actor="customer_alex",
            event_type="TICKET_CREATED",
            old_value=None,
            new_value={"status": "OPEN"},
            at=12,
        ),
        dict(
            key="h_rich_assigned",
            ticket="rich",
            actor="admin",
            event_type="TICKET_ASSIGNED",
            old_value={"assignee_user_id": None},
            new_value={"assignee_user_id": "agent_aria"},
            at=18,
        ),
        dict(
            key="h_rich_priority",
            ticket="rich",
            actor="agent_aria",
            event_type="PRIORITY_CHANGED",
            old_value={"priority": "NORMAL"},
            new_value={"priority": "HIGH"},
            at=19,
        ),
        dict(
            key="h_rich_comment",
            ticket="rich",
            actor="customer_alex",
            event_type="COMMENT_ADDED",
            old_value=None,
            new_value=None,
            at=29,
        ),
    ]


def notifications() -> list[dict]:
    return [
        dict(
            key="n_aria_assigned_rich",
            recipient="agent_aria",
            ticket="rich",
            type=NotificationType.TICKET_ASSIGNED,
            title="Ticket assigned to you",
            message="Ticket #10012 was assigned to you.",
            is_read=False,
            at=18,
        ),
        dict(
            key="n_aria_assigned_printer",
            recipient="agent_aria",
            ticket="open_assigned",
            type=NotificationType.TICKET_ASSIGNED,
            title="Ticket assigned to you",
            message="Ticket #10002 was assigned to you.",
            is_read=True,
            at=13,
        ),
        dict(
            key="n_alex_status_vpn",
            recipient="customer_alex",
            ticket="resolved",
            type=NotificationType.STATUS_CHANGED,
            title="Ticket status updated",
            message="Ticket #10005 is now RESOLVED.",
            is_read=False,
            at=16,
        ),
        dict(
            key="n_alex_priority_rich",
            recipient="customer_alex",
            ticket="rich",
            type=NotificationType.PRIORITY_CHANGED,
            title="Ticket priority updated",
            message="Ticket #10012 priority is now HIGH.",
            is_read=False,
            at=19,
        ),
        dict(
            key="n_alex_comment_printer",
            recipient="customer_alex",
            ticket="open_assigned",
            type=NotificationType.NEW_COMMENT,
            title="New comment on a ticket",
            message="A new comment was added to ticket #10002.",
            is_read=True,
            at=20,
        ),
        dict(
            key="n_jamie_status_waiting",
            recipient="customer_jamie",
            ticket="ben_waiting",
            type=NotificationType.STATUS_CHANGED,
            title="Ticket status updated",
            message="Ticket #10011 is now WAITING_ON_CUSTOMER.",
            is_read=False,
            at=11,
        ),
        dict(
            key="n_ben_assigned_waiting",
            recipient="agent_ben",
            ticket="ben_waiting",
            type=NotificationType.TICKET_ASSIGNED,
            title="Ticket assigned to you",
            message="Ticket #10011 was assigned to you.",
            is_read=False,
            at=11,
        ),
        dict(
            key="n_ben_comment_in_progress",
            recipient="agent_ben",
            ticket="ben_in_progress",
            type=NotificationType.NEW_COMMENT,
            title="New comment on a ticket",
            message="A new comment was added to ticket #10010.",
            is_read=True,
            at=10,
        ),
        dict(
            key="n_owner_msg_ben",
            recipient="owner",
            conversation="conv_ben_owner",
            type=NotificationType.STAFF_MESSAGE_RECEIVED,
            title="New private message from QA Agent Ben",
            message="A staff member sent you a private message.",
            is_read=False,
            at=46,
        ),
        dict(
            key="n_aria_owner_reply",
            recipient="agent_aria",
            conversation="conv_aria_owner",
            type=NotificationType.OWNER_MESSAGE_RECEIVED,
            title="The Owner replied to you",
            message="The Owner sent you a private message.",
            is_read=False,
            at=42,
        ),
        dict(
            key="n_admin_escalation_alex",
            recipient="admin",
            ticket="open_unassigned",
            type=NotificationType.ESCALATION_CREATED,
            title="New account request",
            message="An account-management request needs review.",
            is_read=False,
            at=43,
        ),
        dict(
            key="n_ben_escalation_approved",
            recipient="agent_ben",
            ticket="ben_waiting",
            type=NotificationType.ESCALATION_UPDATED,
            title="Your account request was updated",
            message="Your account-management request is now APPROVED.",
            is_read=True,
            at=48,
        ),
    ]


def staff_conversations() -> list[dict]:
    return [
        dict(
            key="conv_aria_owner",
            staff="agent_aria",
            subject="Escalation process for account recovery",
            at=40,
        ),
        dict(
            key="conv_ben_owner",
            staff="agent_ben",
            subject="Refund tooling permissions",
            at=45,
        ),
    ]


def staff_messages() -> list[dict]:
    return [
        dict(
            key="msg_aria_1",
            conversation="conv_aria_owner",
            sender="agent_aria",
            body=(
                "Hi, I have a customer locked out after a password reset. "
                "Should I open an account request?"
            ),
            read=True,
            at=41,
        ),
        dict(
            key="msg_owner_1",
            conversation="conv_aria_owner",
            sender="owner",
            body=(
                "Yes - attach the ticket and note what you verified. "
                "I will review it today."
            ),
            read=False,
            at=42,
        ),
        dict(
            key="msg_ben_1",
            conversation="conv_ben_owner",
            sender="agent_ben",
            body=(
                "Do I have permission to issue refunds up to 100 EUR, "
                "or should I ask you first?"
            ),
            read=False,
            at=46,
        ),
    ]


def account_requests() -> list[dict]:
    return [
        dict(
            key="req_alex_recovery",
            target="customer_alex",
            ticket="open_unassigned",
            category=EscalationCategory.ACCOUNT_RECOVERY,
            justification=(
                "The customer cannot access the portal after a password reset; "
                "the account may need a recovery step."
            ),
            internal_details="Verified identity over the registered phone number.",
            status=EscalationStatus.PENDING,
            creator="agent_aria",
            decision=None,
            at=43,
        ),
        dict(
            key="req_jamie_profile",
            target="customer_jamie",
            ticket="ben_waiting",
            category=EscalationCategory.PROFILE_CORRECTION,
            justification=(
                "Billing name on the account does not match the legal entity "
                "name provided by the customer."
            ),
            internal_details=None,
            status=EscalationStatus.APPROVED,
            creator="agent_ben",
            decision=dict(
                by="admin",
                reason="Approved - update through the standard profile process.",
                at=48,
            ),
            at=44,
        ),
    ]


def account_request_events() -> list[dict]:
    return [
        dict(
            key="ev_alex_created",
            request="req_alex_recovery",
            actor="agent_aria",
            event_type="REQUEST_CREATED",
            old_value=None,
            new_value={"status": "PENDING", "category": "ACCOUNT_RECOVERY"},
            at=43,
        ),
        dict(
            key="ev_jamie_created",
            request="req_jamie_profile",
            actor="agent_ben",
            event_type="REQUEST_CREATED",
            old_value=None,
            new_value={"status": "PENDING", "category": "PROFILE_CORRECTION"},
            at=44,
        ),
        dict(
            key="ev_jamie_approved",
            request="req_jamie_profile",
            actor="admin",
            event_type="STATUS_CHANGED",
            old_value={"status": "PENDING"},
            new_value={
                "status": "APPROVED",
                "reason": "Approved - update through the standard profile process.",
            },
            at=48,
        ),
    ]


# A 1x1 transparent PNG - a valid, tiny, safe binary test asset.
_PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d494844520000000100000001080600000"
    "01f15c4890000000d4944415478da63fcffff3f030005000101a5f645"
    "0000000049454e44ae426082"
)


def attachments() -> list[dict]:
    return [
        dict(
            key="a_rich_notes",
            ticket="rich",
            uploader="customer_alex",
            filename="shared-drive-error.txt",
            content_type="text/plain",
            content=b"Access denied when opening \\\\fileserver\\Projects\n",
            at=33,
        ),
        dict(
            key="a_rich_screenshot",
            ticket="rich",
            uploader="customer_alex",
            filename="access-denied.png",
            content_type="image/png",
            content=_PNG_BYTES,
            at=34,
        ),
    ]


# --------------------------------------------------------------------------- #
# Seeding
# --------------------------------------------------------------------------- #


async def _get_user_by_email(session, email: str) -> User | None:
    return (await session.exec(select(User).where(User.email == email))).first()


async def _get_user_by_username(session, username: str) -> User | None:
    return (await session.exec(select(User).where(User.username == username))).first()


async def _seed_users(session) -> dict[str, User]:
    users: dict[str, User] = {}
    existing_owner = (
        await session.exec(select(User).where(User.role == Role.OWNER))
    ).first()

    for spec in personas():
        desired_role = spec["role"]
        # The database permits only one OWNER. Reuse whatever exists.
        if desired_role == Role.OWNER and existing_owner is not None:
            users[spec["key"]] = existing_owner
            continue

        user = await _get_user_by_email(session, spec["email"])
        if user is None:
            user = User(
                id=_uid("user", spec["key"]),
                clerk_id=spec["clerk_id"],
                full_name=spec["full_name"],
                username=spec["username"],
                email=spec["email"],
                role=desired_role,
                is_active=spec["is_active"],
                created_at=_at(0),
                updated_at=_at(0),
            )
            session.add(user)
            await session.flush()
            # A deterministic id can only collide if a previous run created it
            # under a different natural key; fall back to the natural key.
        else:
            # For the Owner fixture only, align the role/status so a manually
            # provisioned placeholder becomes the QA Owner. Nothing else is
            # overwritten for existing accounts.
            if desired_role == Role.OWNER and user.role != Role.OWNER:
                user.role = Role.OWNER
                user.is_active = True
            session.add(user)

        users[spec["key"]] = user
        if user.role == Role.OWNER:
            existing_owner = user

    await session.commit()
    for user in users.values():
        await session.refresh(user)
    return users


async def _get_ticket_by_number(session, number: int) -> Ticket | None:
    return (
        await session.exec(select(Ticket).where(Ticket.ticket_number == number))
    ).first()


async def _seed_tickets(session, users: dict[str, User]) -> dict[str, Ticket]:
    """Create or reuse the fixture tickets, keyed by their deterministic id.

    The ticket-number space is shared with the application's own tickets, so
    a fixture number can already be taken by a foreign row on a database where
    app activity happened first. Such a row is never adopted as the fixture
    (that would silently replace seed data with unrelated tickets): the
    fixture is created under a fresh number above every number in use and a
    warning is logged. On a clean QA database the stable fixture numbers are
    used exactly as specified.
    """
    specs = tickets()
    result: dict[str, Ticket] = {}
    highest = (await session.exec(select(func.max(Ticket.ticket_number)))).one()
    next_free = max(highest or 0, *(spec["number"] for spec in specs))

    for spec in specs:
        ticket = await session.get(Ticket, _uid("ticket", spec["key"]))
        if ticket is None:
            number = spec["number"]
            if await _get_ticket_by_number(session, number) is not None:
                next_free += 1
                logger.warning(
                    "QA seed: ticket number %s is held by a non-fixture ticket; "
                    "seeding %r as #%s instead of adopting it",
                    number,
                    spec["key"],
                    next_free,
                )
                number = next_free
            assignee = users.get(spec["assignee"]) if spec["assignee"] else None
            ticket = Ticket(
                id=_uid("ticket", spec["key"]),
                ticket_number=number,
                title=spec["title"],
                description=spec["description"],
                status=spec["status"],
                priority=spec["priority"],
                category=spec.get("category", TicketCategory.OTHER),
                created_by_user_id=users[spec["owner"]].id,
                assignee_user_id=assignee.id if assignee else None,
                assigned_at=_at(spec["at"] + 1) if assignee else None,
                created_at=_at(spec["at"]),
                updated_at=_at(spec["at"]),
                resolved_at=_at(spec["at"] + 5) if spec.get("resolved") else None,
            )
            session.add(ticket)
            await session.flush()
        result[spec["key"]] = ticket

    await session.commit()
    for ticket in result.values():
        await session.refresh(ticket)
    return result


async def _seed_comments(
    session, users: dict[str, User], tickets: dict[str, Ticket]
) -> int:
    created = 0
    for spec in comments():
        comment_id = _uid("comment", spec["key"])
        if await session.get(Comment, comment_id) is not None:
            continue
        session.add(
            Comment(
                id=comment_id,
                ticket_id=tickets[spec["ticket"]].id,
                author_user_id=users[spec["author"]].id,
                body=spec["body"],
                is_internal=spec["internal"],
                created_at=_at(spec["at"]),
            )
        )
        created += 1
    await session.commit()
    return created


def _resolve_assignee_value(value: object, users: dict[str, User]) -> object:
    if isinstance(value, str) and value in users:
        return str(users[value].id)
    return value


async def _seed_history(
    session, users: dict[str, User], tickets: dict[str, Ticket]
) -> int:
    created = 0
    for spec in history_events():
        entry_id = _uid("history", spec["key"])
        if await session.get(TicketHistory, entry_id) is not None:
            continue
        old_value = spec["old_value"]
        new_value = spec["new_value"]
        if isinstance(old_value, dict):
            old_value = {
                k: _resolve_assignee_value(v, users) for k, v in old_value.items()
            }
        if isinstance(new_value, dict):
            new_value = {
                k: _resolve_assignee_value(v, users) for k, v in new_value.items()
            }
        session.add(
            TicketHistory(
                id=entry_id,
                ticket_id=tickets[spec["ticket"]].id,
                actor_user_id=users[spec["actor"]].id,
                event_type=spec["event_type"],
                old_value=old_value,
                new_value=new_value,
                created_at=_at(spec["at"]),
            )
        )
        created += 1
    await session.commit()
    return created


async def _seed_notifications(
    session,
    users: dict[str, User],
    tickets: dict[str, Ticket],
    conversations: dict[str, StaffConversation] | None = None,
) -> int:
    conversations = conversations or {}
    created = 0
    for spec in notifications():
        notification_id = _uid("notification", spec["key"])
        if await session.get(Notification, notification_id) is not None:
            continue
        ticket_key = spec.get("ticket")
        conversation_key = spec.get("conversation")
        session.add(
            Notification(
                id=notification_id,
                recipient_user_id=users[spec["recipient"]].id,
                related_ticket_id=(tickets[ticket_key].id if ticket_key else None),
                related_conversation_id=(
                    conversations[conversation_key].id if conversation_key else None
                ),
                type=spec["type"],
                title=spec["title"],
                message=spec["message"],
                is_read=spec["is_read"],
                created_at=_at(spec["at"]),
            )
        )
        created += 1
    await session.commit()
    return created


async def _seed_staff_conversations(
    session, users: dict[str, User]
) -> dict[str, StaffConversation]:
    result: dict[str, StaffConversation] = {}
    for spec in staff_conversations():
        conversation_id = _uid("staff_conversation", spec["key"])
        conversation = await session.get(StaffConversation, conversation_id)
        if conversation is None:
            conversation = StaffConversation(
                id=conversation_id,
                staff_user_id=users[spec["staff"]].id,
                owner_user_id=users["owner"].id,
                subject=spec["subject"],
                created_at=_at(spec["at"]),
                updated_at=_at(spec["at"]),
            )
            session.add(conversation)
            await session.flush()
        result[spec["key"]] = conversation
    await session.commit()
    return result


async def _seed_staff_messages(
    session,
    users: dict[str, User],
    conversations: dict[str, StaffConversation],
) -> int:
    created = 0
    for spec in staff_messages():
        message_id = _uid("staff_message", spec["key"])
        if await session.get(StaffMessage, message_id) is not None:
            continue
        session.add(
            StaffMessage(
                id=message_id,
                conversation_id=conversations[spec["conversation"]].id,
                sender_user_id=users[spec["sender"]].id,
                body=spec["body"],
                created_at=_at(spec["at"]),
                read_at=_at(spec["at"] + 2) if spec["read"] else None,
            )
        )
        created += 1
    await session.commit()

    # Keep the inbox ordering deterministic: last_message_at mirrors the
    # newest seeded message, whether it was just created or already present.
    for conversation in conversations.values():
        latest = (
            await session.exec(
                select(StaffMessage)
                .where(StaffMessage.conversation_id == conversation.id)
                .order_by(StaffMessage.created_at.desc())
                .limit(1)
            )
        ).first()
        if latest is not None and conversation.last_message_at != latest.created_at:
            conversation.last_message_at = latest.created_at
            session.add(conversation)
    await session.commit()
    return created


async def _seed_account_requests(
    session,
    users: dict[str, User],
    tickets: dict[str, Ticket],
) -> dict[str, AccountManagementRequest]:
    result: dict[str, AccountManagementRequest] = {}
    for spec in account_requests():
        request_id = _uid("account_request", spec["key"])
        request = await session.get(AccountManagementRequest, request_id)
        if request is None:
            target = users[spec["target"]]
            decision = spec.get("decision")
            request = AccountManagementRequest(
                id=request_id,
                target_user_id=target.id,
                target_full_name_snapshot=target.full_name,
                target_email_snapshot=target.email,
                ticket_id=tickets[spec["ticket"]].id if spec.get("ticket") else None,
                category=spec["category"],
                justification=spec["justification"],
                internal_details=spec["internal_details"],
                status=spec["status"],
                decision_reason=decision["reason"] if decision else None,
                decided_by_user_id=(users[decision["by"]].id if decision else None),
                decided_at=_at(decision["at"]) if decision else None,
                created_by_user_id=users[spec["creator"]].id,
                created_at=_at(spec["at"]),
                updated_at=_at(spec["at"]),
            )
            session.add(request)
            await session.flush()
        result[spec["key"]] = request
    await session.commit()
    return result


async def _seed_account_request_events(
    session,
    users: dict[str, User],
    requests: dict[str, AccountManagementRequest],
) -> int:
    created = 0
    for spec in account_request_events():
        event_id = _uid("account_request_event", spec["key"])
        if await session.get(AccountRequestEvent, event_id) is not None:
            continue
        session.add(
            AccountRequestEvent(
                id=event_id,
                request_id=requests[spec["request"]].id,
                actor_user_id=users[spec["actor"]].id,
                event_type=spec["event_type"],
                old_value=spec["old_value"],
                new_value=spec["new_value"],
                created_at=_at(spec["at"]),
            )
        )
        created += 1
    await session.commit()
    return created


def _storage_key(spec: dict) -> str:
    return f"qa-{_uid('attachment', spec['key']).hex[:12]}-{spec['filename']}"


async def _seed_attachments(
    session,
    users: dict[str, User],
    tickets: dict[str, Ticket],
    upload_root: Path,
) -> int:
    upload_root.mkdir(parents=True, exist_ok=True)
    created = 0
    for spec in attachments():
        attachment_id = _uid("attachment", spec["key"])
        storage_key = _storage_key(spec)
        destination = upload_root / storage_key
        if await session.get(Attachment, attachment_id) is None:
            session.add(
                Attachment(
                    id=attachment_id,
                    ticket_id=tickets[spec["ticket"]].id,
                    uploaded_by_user_id=users[spec["uploader"]].id,
                    original_filename=spec["filename"],
                    storage_key=storage_key,
                    content_type=spec["content_type"],
                    size_bytes=len(spec["content"]),
                    scan_status=AttachmentScanStatus.CLEAN,
                    created_at=_at(spec["at"]),
                )
            )
            created += 1
        # Write (or repair) the file so a download always succeeds.
        if not destination.exists():
            destination.write_bytes(spec["content"])
    await session.commit()
    return created


async def seed(upload_root: Path, session_factory=None) -> dict[str, int]:
    factory = session_factory or async_session
    async with factory() as session:
        users = await _seed_users(session)
        tickets_map = await _seed_tickets(session, users)
        conversations = await _seed_staff_conversations(session, users)
        request_map = await _seed_account_requests(session, users, tickets_map)
        comment_count = await _seed_comments(session, users, tickets_map)
        history_count = await _seed_history(session, users, tickets_map)
        message_count = await _seed_staff_messages(session, users, conversations)
        request_event_count = await _seed_account_request_events(
            session, users, request_map
        )
        notification_count = await _seed_notifications(
            session, users, tickets_map, conversations
        )
        attachment_count = await _seed_attachments(
            session, users, tickets_map, upload_root
        )

        totals = {
            "users": (await session.exec(select(func.count()).select_from(User))).one(),
            "tickets": (
                await session.exec(select(func.count()).select_from(Ticket))
            ).one(),
            "comments": (
                await session.exec(select(func.count()).select_from(Comment))
            ).one(),
            "history": (
                await session.exec(select(func.count()).select_from(TicketHistory))
            ).one(),
            "notifications": (
                await session.exec(select(func.count()).select_from(Notification))
            ).one(),
            "attachments": (
                await session.exec(select(func.count()).select_from(Attachment))
            ).one(),
            "staff_conversations": (
                await session.exec(select(func.count()).select_from(StaffConversation))
            ).one(),
            "staff_messages": (
                await session.exec(select(func.count()).select_from(StaffMessage))
            ).one(),
            "account_requests": (
                await session.exec(
                    select(func.count()).select_from(AccountManagementRequest)
                )
            ).one(),
            "account_request_events": (
                await session.exec(
                    select(func.count()).select_from(AccountRequestEvent)
                )
            ).one(),
        }

    totals["_created_comments"] = comment_count
    totals["_created_history"] = history_count
    totals["_created_notifications"] = notification_count
    totals["_created_attachments"] = attachment_count
    totals["_created_staff_messages"] = message_count
    totals["_created_account_request_events"] = request_event_count
    return totals


async def _main(environ: dict[str, str]) -> int:
    try:
        assert_seed_enabled(environ)
        assert_safe_target(settings.DATABASE_URL)
        upload_root = assert_safe_upload_dir(settings.UPLOAD_DIR)
    except SeedRefused as exc:
        print(f"QA seed refused: {exc}", file=sys.stderr)
        return 1

    totals = await seed(upload_root)

    # A short, secret-free summary for the operator.
    print("QA seed complete.")
    print(f"  database      : {settings.DATABASE_URL.rsplit('@', 1)[-1]}")
    print(f"  upload dir    : {upload_root}")
    print(f"  users         : {totals['users']}")
    print(f"  tickets       : {totals['tickets']}")
    print(f"  comments      : {totals['comments']}")
    print(f"  history       : {totals['history']}")
    print(f"  notifications : {totals['notifications']}")
    print(f"  attachments   : {totals['attachments']}")
    return 0


def main() -> int:
    """Synchronous entry point for ``python -m app.commands.seed_qa_data``."""
    import os

    return asyncio.run(_main(dict(os.environ)))


if __name__ == "__main__":
    raise SystemExit(main())
