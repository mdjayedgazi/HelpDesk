"""Seed the demo database with a realistic, interconnected dataset.

This is the canonical demo seeder for the live HelpDesk deployment. It exists so
the Owner can sign in to the real application and browse a coherent, realistic
dataset. It is deliberately separate from ``app.commands.seed_qa_data`` (which
targets a loopback-only isolated QA database):

* this command refuses loopback hosts and any database whose name starts with
  ``helpdesk_qa``;
* ``seed_qa_data`` refuses any non-loopback host, so it can never touch Neon.

Dataset shape
-------------
The dataset is described by a :class:`DemoPlan`. Two sizes are supported:

* ``--size 100`` (default): 100 users total (the preserved Owner + 8 ADMIN +
  20 AGENT + 71 CUSTOMER), 300 tickets, ~790 comments, ~520 notifications.
* ``--size 50``: 50 users total (Owner + 4 + 10 + 35), 150 tickets, scaled
  comments/notifications.

The database enforces exactly **one** Owner (partial unique index
``uq_users_single_owner``), so no size creates a second Owner. Tickets are
spread across the last 45 days with the most recent 14 days deliberately well
populated, so the analytics trend, aging counts and "created today" scenarios
are all real. Timestamps are anchored to the moment the seed runs.

Safety model (all must hold before a single row is written)
----------------------------------------------------------
* ``HELPDESK_DEMO_SEED_CONFIRM`` (or ``--confirm``) must equal the exact demo
  namespace **and** target identity token, e.g.
  ``HD-DEMO-20261019 @ ep-...neon.tech/neondb``;
* the configured ``DATABASE_URL`` host and database name must match the verified
  target constants below;
* a single OWNER must already exist (the preserved Owner) and must be unchanged
  after the run (the row is hashed before and after and rolled back on drift);
* the environment must not be declared ``production``/``prod`` unless the
  deliberate ``HELPDESK_DEMO_ALLOW_PRODUCTION`` override is set (needed for the
  Railway ``college-demo`` profile, which declares itself production);
* the attachment upload directory must live under ``/tmp``.

Everything it writes belongs to the demo namespace ``HD-DEMO-20261019`` and uses
deterministic uuid5 identifiers, so re-running adds nothing and duplicates
nothing. It never truncates or deletes anything, never runs on application
startup, and never touches the Owner or any record outside its namespace.

Usage (from ``backend/`` with the project environment active)::

    # Preview the full plan - no database connection, no writes.
    uv run python -m app.commands.seed_demo_data --dry-run --size 100

    # Insert (idempotent; refuses without the confirmation token).
    HELPDESK_DEMO_SEED_CONFIRM='HD-DEMO-20261019 @ <host>/neondb' \
    HELPDESK_DEMO_UPLOAD_DIR=/tmp/helpdesk-demo-uploads \
    uv run python -m app.commands.seed_demo_data --size 100

Add ``--verify-only`` to re-read and report the seeded namespace without
inserting anything. Add ``--json`` for machine-readable output. See
``docs/demo-data-seeding.md`` for the full runbook.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import sys
import urllib.parse
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import func, or_, text
from sqlmodel import select

from app.core.config import settings
from app.core.database import async_session
from app.enums.enums import (
    AttachmentScanStatus,
    EscalationCategory,
    EscalationStatus,
    InternalAudience,
    NotificationType,
    Role,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)
from app.models import (
    AccountManagementRequest,
    AccountRequestComment,
    AccountRequestEvent,
    Attachment,
    Comment,
    InternalMessage,
    InternalMessageRecipient,
    Notification,
    StaffConversation,
    StaffMessage,
    Ticket,
    TicketFeedback,
    TicketHistory,
    User,
)
from app.services.tickets import TICKET_NUMBER_START

# --------------------------------------------------------------------------- #
# Namespace and target identity
# --------------------------------------------------------------------------- #

MARKER = "HD-DEMO-20261019"
CONFIRM_ENV = "HELPDESK_DEMO_SEED_CONFIRM"
UPLOAD_ENV = "HELPDESK_DEMO_UPLOAD_DIR"

# The verified Neon *development* target. Changing these constants (a reviewed
# change) is required before this command can ever write anywhere else.
EXPECTED_HOST = "ep-proud-surf-b5oyh4qr-pooler.c-7.us-east-2.aws.neon.tech"
EXPECTED_DB = "neondb"
EXPECTED_TOKEN = f"{MARKER} @ {EXPECTED_HOST}/{EXPECTED_DB}"

DEMO_UPLOAD_DIR = "/tmp/helpdesk-demo-uploads"

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}

_NAMESPACE = uuid.uuid5(
    uuid.NAMESPACE_URL, f"https://helpdesk.demo.local/neon/{MARKER}"
)

# --------------------------------------------------------------------------- #
# Dataset plan (size, distribution, time anchor)
# --------------------------------------------------------------------------- #

# The demo timeline is anchored to the moment the seed runs, not a frozen
# constant. The analytics endpoint derives its 14-day window from
# ``datetime.now(UTC)``, so a fixed base date would place every ticket outside
# the window and render the volume trend as a flat zero line. Anchoring to
# ``now`` is what makes the seeded data produce a real trend, real aging counts
# and real "created today" rows. Determinism is preserved because every offset
# is derived from the same anchor and a fixed RNG seed.
SCENARIO_SPAN_DAYS = 45
MINUTES_PER_DAY = 24 * 60
MAX_SPAN_MINUTES = SCENARIO_SPAN_DAYS * MINUTES_PER_DAY
RNG_SEED = 20261019

# Role distribution. The database enforces exactly ONE owner (partial unique
# index ``uq_users_single_owner``), so the brief's "2 owners" is intentionally
# rendered as one Owner plus an extra Administrator. See docs/demo-data-audit.md.
_ROLE_SPLITS: dict[int, tuple[int, int, int]] = {
    # size -> (admins, agents, customers); the Owner is additional.
    100: (8, 20, 71),
    50: (4, 10, 35),
}

# Tickets per size. Roughly 3 tickets per user at 100, scaled down at 50.
_TICKET_COUNTS: dict[int, int] = {100: 300, 50: 150}

# Relative status/priority weights (largest-remainder rounded to the exact
# ticket count). They reproduce the brief's 300-ticket targets exactly:
# status 60/60/60/90/30 and priority 45/135/90/30.
_STATUS_WEIGHTS = {
    TicketStatus.OPEN: 1.0,
    TicketStatus.IN_PROGRESS: 1.0,
    TicketStatus.WAITING_ON_CUSTOMER: 1.0,
    TicketStatus.RESOLVED: 1.5,
    TicketStatus.CLOSED: 0.5,
}
_PRIORITY_WEIGHTS = {
    TicketPriority.LOW: 0.15,
    TicketPriority.NORMAL: 0.45,
    TicketPriority.HIGH: 0.3,
    TicketPriority.URGENT: 0.1,
}


@dataclass(frozen=True)
class DemoPlan:
    """Everything a single seed run needs to be reproducible and sized."""

    size: int
    admins: int
    agents: int
    customers: int
    tickets: int
    staff_conversations: int
    account_requests: int
    attachments: int
    anchor: datetime

    @property
    def demo_users(self) -> int:
        return self.admins + self.agents + self.customers

    @property
    def users_total(self) -> int:
        # +1 for the preserved Owner.
        return self.demo_users + 1


def _split_counts(total: int, weights: dict) -> dict:
    """Largest-remainder apportionment of ``total`` over ``weights``.

    Deterministic and exact: the returned counts always sum to ``total``.
    """
    weight_sum = sum(weights.values()) or 1.0
    raw = {key: total * weight / weight_sum for key, weight in weights.items()}
    counts = {key: int(value) for key, value in raw.items()}
    remainder = total - sum(counts.values())
    # Hand out the leftover units to the largest fractional parts, breaking ties
    # by the enum order for stability.
    order = sorted(
        raw, key=lambda key: (-(raw[key] - counts[key]), list(weights).index(key))
    )
    for key in order[:remainder]:
        counts[key] += 1
    return counts


def plan_for(size: int, *, anchor: datetime | None = None) -> DemoPlan:
    """Build a validated dataset plan for a supported size."""
    if size not in _ROLE_SPLITS:
        raise SeedRefused(
            f"Unsupported --size {size}. Supported sizes: {sorted(_ROLE_SPLITS)}."
        )
    admins, agents, customers = _ROLE_SPLITS[size]
    return DemoPlan(
        size=size,
        admins=admins,
        agents=agents,
        customers=customers,
        tickets=_TICKET_COUNTS[size],
        staff_conversations=max(8, min(agents, 12)),
        account_requests=12 if size >= 100 else 6,
        attachments=12 if size >= 100 else 6,
        anchor=(anchor or datetime.now(UTC)).replace(microsecond=0),
    )


# The plan is resolved once per run and read by the deterministic spec
# builders. It is ``None`` until an entry point sets it; the default keeps the
# pure helper functions usable in isolation (tests, exploratory calls).
_ACTIVE_PLAN: DemoPlan | None = None


def active_plan() -> DemoPlan:
    global _ACTIVE_PLAN
    if _ACTIVE_PLAN is None:
        _ACTIVE_PLAN = plan_for(100)
    return _ACTIVE_PLAN


def use_plan(plan: DemoPlan) -> DemoPlan:
    """Install ``plan`` as the active plan for this run and return it."""
    global _ACTIVE_PLAN
    _ACTIVE_PLAN = plan
    return plan


# Backwards-compatible module constants (the 100-user defaults). Existing
# tests and callers read these; the active plan overrides them at runtime.
N_ADMINS = _ROLE_SPLITS[100][0]
N_AGENTS = _ROLE_SPLITS[100][1]
N_CUSTOMERS = _ROLE_SPLITS[100][2]
N_TICKETS = _TICKET_COUNTS[100]
N_STAFF_CONVERSATIONS = 12
N_ACCOUNT_REQUESTS = 12
N_ATTACHMENTS = 12

# Inactive accounts at 100 users (scaled proportionally for 50). Kept small and
# deliberate: a realistic mix, never the Owner.
_INACTIVE_CUSTOMER_INDEXES = {55, 62, 69}
_INACTIVE_AGENT_INDEXES = {18, 19}


class SeedRefused(RuntimeError):
    """Raised for any condition that makes seeding unsafe."""


def _uid(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(_NAMESPACE, f"{kind}:{key}")


def _at(minutes: int) -> datetime:
    """A timestamp ``minutes`` from the run anchor (negative = in the past)."""
    return active_plan().anchor + timedelta(minutes=minutes)


def _hours(start_minutes: int, hours: float) -> datetime:
    return _at(start_minutes) + timedelta(hours=hours)


def _parsed(url: str) -> urllib.parse.ParseResult:
    return urllib.parse.urlparse(url)


def redacted_target(url: str) -> str:
    """A secret-free ``host/database`` description of the configured target."""
    parsed = _parsed(url)
    host = parsed.hostname or "?"
    name = (parsed.path or "").lstrip("/") or "?"
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


# Opt-in override for the one deployment that is *declared* production but is
# the intended demo target (Railway's `college-demo` profile). Supplying this
# value is itself a deliberate, explicit act; it does not skip any other guard
# (confirm token, host match, /tmp uploads, Owner hash, atomic rollback).
PRODUCTION_OVERRIDE_ENV = "HELPDESK_DEMO_ALLOW_PRODUCTION"
PRODUCTION_OVERRIDE_VALUE = "I-UNDERSTAND-THIS-IS-THE-DEMO-DATABASE"


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
    if declared not in {"production", "prod"}:
        return
    # The demo deployment declares itself production. Allow it only with the
    # exact override phrase, and only for the verified demo host (checked
    # separately by assert_neon_target).
    override = (environ.get(PRODUCTION_OVERRIDE_ENV) or "").strip()
    if override != PRODUCTION_OVERRIDE_VALUE:
        raise SeedRefused(
            "Refusing to seed: the environment is declared production. If this is "
            "the college-demo database, set "
            f"{PRODUCTION_OVERRIDE_ENV}={PRODUCTION_OVERRIDE_VALUE} explicitly."
        )


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
            f"Refusing to write demo attachments outside /tmp (got {root}). "
            f"Run with {UPLOAD_ENV}={DEMO_UPLOAD_DIR}."
        )
    return root


# --------------------------------------------------------------------------- #
# Realistic demo content (deterministic)
# --------------------------------------------------------------------------- #

_FIRST_NAMES = [
    "Amara",
    "Noah",
    "Priya",
    "Liam",
    "Yuki",
    "Mateo",
    "Zara",
    "Ethan",
    "Aisha",
    "Diego",
    "Freya",
    "Omar",
    "Ingrid",
    "Kai",
    "Lucia",
    "Ravi",
    "Sofia",
    "Tomas",
    "Nadia",
    "Elias",
    "Mei",
    "Jonas",
    "Clara",
    "Hassan",
    "Elif",
    "Marco",
    "Lena",
    "Idris",
    "Rosa",
    "Anton",
    "Nadia2",
    "Hugo",
    "Anika",
    "Samir",
    "Greta",
    "Yusuf",
    "Paula",
    "Dmitri",
    "Céline",
    "Arjun",
    "Nora",
    "Kofi",
    "Vera",
    "Bilal",
    "Astrid",
    "Ren",
    "Camila",
    "Oskar",
    "Leila",
    "Bruno",
    "Signe",
    "Amir",
    "Tessa",
    "Pavel",
    "Rania",
    "Felix",
    "Ines",
    "Sven",
    "Amina",
    "Theo",
]

_LAST_NAMES = [
    "Okafor",
    "Bergström",
    "Nakamura",
    "Silva",
    "Kowalski",
    "Haddad",
    "Rossi",
    "Andersen",
    "Novak",
    "Fischer",
    "Moreau",
    "Ivanov",
    "Costa",
    "Lindholm",
    "Farah",
    "Weber",
    "Duarte",
    "Karlsson",
    "Mensah",
    "Petrov",
    "Almeida",
    "Bianchi",
    "Sørensen",
    "Yilmaz",
    "Jensen",
    "Nguyen",
    "O'Connor",
    "Vargas",
    "Schmidt",
    "Larsen",
    "Ahmadi",
    "Bauer",
    "Ricci",
    "Dahl",
    "Bakker",
    "Fernández",
    "Krüger",
    "Sato",
    "Popa",
    "Lund",
    "Horvat",
    "Marchetti",
    "Holm",
    "Kaminski",
    "Reyes",
    "Steiner",
    "Voss",
    "Iqbal",
    "Cruz",
    "Meyer",
]

_TICKET_TEMPLATES: dict[TicketCategory, list[tuple[str, str]]] = {
    TicketCategory.BILLING: [
        (
            "Incorrect charge on latest invoice",
            "Our latest invoice shows a duplicate line item that we did not "
            "authorize. Please review the billing period and issue a correction.",
        ),
        (
            "Refund not received after cancellation",
            "We cancelled the subscription two weeks ago and were told a refund "
            "would arrive within five business days. It has not appeared yet.",
        ),
        (
            "Need a copy of last quarter's invoices",
            "Finance is closing the books and needs downloadable copies of all "
            "invoices issued last quarter for our records.",
        ),
    ],
    TicketCategory.ACCOUNT_ACCESS: [
        (
            "Cannot reset my password",
            "The password reset email never arrives. I have checked spam and "
            "confirmed the address is correct. I am locked out of my account.",
        ),
        (
            "Two-factor prompts rejected",
            "The authenticator codes are always reported as invalid even though "
            "the device clock is synced. I cannot complete sign-in.",
        ),
        (
            "Locked out after changing phone",
            "I replaced my phone and no longer receive verification codes. I need "
            "help restoring access to my account.",
        ),
    ],
    TicketCategory.TECHNICAL: [
        (
            "Dashboard fails to load intermittently",
            "Roughly one in three page loads shows a blank dashboard. A refresh "
            "usually fixes it. This started after the last release.",
        ),
        (
            "Export produces an empty file",
            "Exporting the ticket report downloads a zero-byte CSV. The on-screen "
            "data looks correct, so the export step seems broken.",
        ),
        (
            "Search returns stale results",
            "Searching for a closed ticket by its number returns an old cached "
            "copy instead of the current record.",
        ),
    ],
    TicketCategory.OUTAGE: [
        (
            "API returning 502 for all requests",
            "Every call to the API is failing with a gateway error since about an "
            "hour ago. This is blocking our production integration.",
        ),
        (
            "Regional latency spike",
            "Requests from our region are taking several seconds. Other regions "
            "seem unaffected. Is there an incident in progress?",
        ),
        (
            "Webhooks stopped being delivered",
            "We have not received any webhook callbacks since midnight. Endpoint "
            "health checks pass on our side.",
        ),
    ],
    TicketCategory.BUG: [
        (
            "Filter resets when paginating",
            "Applying a status filter and then moving to page two clears the "
            "filter and shows unfiltered results.",
        ),
        (
            "Attachment upload silently fails",
            "Uploading a PDF over a few megabytes appears to succeed but the file "
            "never appears on the ticket.",
        ),
        (
            "Timestamps displayed in the wrong timezone",
            "Ticket timestamps are shown several hours off from our configured "
            "timezone for every record.",
        ),
    ],
    TicketCategory.ACCOUNT_MANAGEMENT: [
        (
            "Request to add a teammate",
            "Please provision an account for a new colleague joining the support "
            "team next week so they can begin onboarding.",
        ),
        (
            "Change the billing contact on our account",
            "Our billing contact has changed. Please update the primary contact "
            "so invoices reach the right person.",
        ),
        (
            "Consolidate two duplicate accounts",
            "We appear to have two accounts after a migration. Please help merge "
            "the history into a single account.",
        ),
    ],
    TicketCategory.OTHER: [
        (
            "General question about data retention",
            "We need to understand how long resolved tickets are retained for our "
            "internal compliance review.",
        ),
        (
            "Feature request: bulk status updates",
            "Our team would benefit from updating the status of many tickets at "
            "once during weekly triage.",
        ),
        (
            "Documentation clarification",
            "The public documentation is ambiguous about how assignment works. "
            "Could you clarify the intended behaviour?",
        ),
    ],
}

_CUSTOMER_COMMENTS = [
    "Thanks for picking this up — happy to provide any extra detail you need.",
    "This is still happening on my side as of this morning.",
    "I have attached a screenshot that shows the exact error.",
    "Confirmed — clearing the cache did not change anything for us.",
    "Any update on this? It is becoming quite disruptive for our team.",
    "We can reproduce this reliably on two different browsers.",
]

_AGENT_COMMENTS = [
    "Thanks for the report. I have reproduced the issue and am investigating.",
    "I have escalated this to the engineering team and will keep you posted.",
    "Could you confirm which plan you are on so I can check the correct limits?",
    "A fix is being prepared; I will update this ticket as soon as it ships.",
    "I have applied a workaround in the meantime — please try again now.",
    "This is resolved on our side. Please confirm everything looks correct.",
]

_RESOLUTION_COMMENTS = [
    "The fix has been deployed — please confirm everything looks correct now.",
    "I have applied the correction and verified it on our side. This is resolved.",
    "Your request has been completed. Let us know if anything else comes up.",
    "This is now working as expected after the change. Marking the ticket resolved.",
]

_INTERNAL_NOTES = [
    "Internal: linked to the same root cause as the outage incident.",
    "Internal: customer is on an enterprise plan — prioritize accordingly.",
    "Internal: awaiting confirmation from the billing system vendor.",
    "Internal: needs a follow-up once the next release is deployed.",
]

_STAFF_SUBJECTS = [
    "Coverage for next week's on-call rotation",
    "Escalation guideline questions",
    "Request to review the new triage policy",
    "Reporting a recurring data-quality issue",
    "Proposal for a shared macro library",
    "Concerns about assignment fairness",
    "Follow-up on last month's incidents",
    "Request for additional dashboard metrics",
    "Process change suggestion",
    "Handover notes for a departing teammate",
    "Question about internal note visibility",
    "Ideas to reduce first-response time",
]

_STAFF_MESSAGES = [
    "Hi — do you have a moment to discuss this? I have a few questions.",
    "Thanks for raising it. I will review and get back to you today.",
    "Agreed, let's align on an approach before the next rotation.",
    "I have added a note to the relevant tickets already.",
    "That works for me. Let's keep this thread for follow-ups.",
    "Understood — I'll own the follow-up action here.",
]

_ESCALATION_JUSTIFICATION = [
    "The customer lost access after replacing their device and cannot complete "
    "the standard recovery flow.",
    "The account's identity must be re-linked to a verified address that the "
    "customer no longer controls.",
    "A protected profile field is incorrect and the customer cannot correct it "
    "themselves.",
    "The customer is requesting a role change that requires owner approval.",
]


@dataclass
class UserSpec:
    key: str
    role: Role
    full_name: str
    username: str
    email: str
    is_active: bool


def demo_users(plan: DemoPlan | None = None) -> list[UserSpec]:
    """The deterministic demo users for the active plan (Owner is additional)."""
    plan = plan or active_plan()
    specs: list[UserSpec] = []

    def make(role: Role, index: int, count: int) -> UserSpec:
        slug = role.value  # customer / agent / admin
        username = f"demo_{slug}_{index:02d}"
        name_index = len(specs)
        full_name = (
            f"{_FIRST_NAMES[name_index % len(_FIRST_NAMES)]} "
            f"{_LAST_NAMES[(name_index * 7) % len(_LAST_NAMES)]}"
        )
        # A deliberate, small inactive minority, scaled to the size. Indexes are
        # scaled so both 50- and 100-user runs get the same *proportion*.
        inactive_customers = {
            round(i * plan.customers / 79) for i in _INACTIVE_CUSTOMER_INDEXES
        }
        inactive_agents = {round(i * plan.agents / 20) for i in _INACTIVE_AGENT_INDEXES}
        if role == Role.CUSTOMER:
            is_active = index not in inactive_customers
        elif role == Role.AGENT:
            is_active = index not in inactive_agents
        else:
            is_active = True
        return UserSpec(
            key=f"{slug}_{index:02d}",
            role=role,
            full_name=full_name,
            username=username,
            email=f"{username}@example.test",
            is_active=is_active,
        )

    for i in range(plan.admins):
        specs.append(make(Role.ADMIN, i, plan.admins))
    for i in range(plan.agents):
        specs.append(make(Role.AGENT, i, plan.agents))
    for i in range(plan.customers):
        specs.append(make(Role.CUSTOMER, i, plan.customers))
    return specs


def _specs_by_role(users: list[UserSpec], role: Role) -> list[UserSpec]:
    return [u for u in users if u.role == role]


def ticket_specs(users: list[UserSpec]) -> list[dict]:
    """Deterministic ticket specs with an exact distribution and real timeline.

    The shape is driven by the active plan:

    * status counts are apportioned to the exact ticket total using the brief's
      target weights (60/60/60/90/30 at 300);
    * priority counts likewise (45/135/90/30 at 300);
    * timestamps are spread over the preceding ``SCENARIO_SPAN_DAYS`` days with
      the most recent 14 days deliberately well populated, so the analytics
      trend, the aging counts and the "created today" scenario are all real;
    * lifecycle timestamps are causally ordered per status (a resolved ticket is
      created, then assigned, then resolved, never the reverse).

    Assignment leaves roughly 15-20% of *active* tickets unassigned so the
    unassigned queue and the assignment-coverage metric are meaningful.
    """
    plan = active_plan()
    customers = _specs_by_role(users, Role.CUSTOMER)
    agents = _specs_by_role(users, Role.AGENT)
    categories = list(TicketCategory)

    status_counts = _split_counts(plan.tickets, _STATUS_WEIGHTS)
    priority_counts = _split_counts(plan.tickets, _PRIORITY_WEIGHTS)

    # Expand the apportioned counts into an ordered list of statuses/priorities.
    statuses: list[TicketStatus] = []
    for status, count in status_counts.items():
        statuses.extend([status] * count)
    priorities: list[TicketPriority] = []
    for priority, count in priority_counts.items():
        priorities.extend([priority] * count)
    if len(statuses) != plan.tickets or len(priorities) != plan.tickets:
        raise SeedRefused("Ticket distribution did not match the planned total.")

    rng = random.Random(RNG_SEED)
    # Creation times are sorted oldest-first, so if statuses were assigned in
    # block order every OPEN ticket would be old and every CLOSED one recent.
    # Shuffle (with the fixed seed) so each status is spread across the whole
    # timeline; this is what makes aging, "created today", and the 14-day
    # resolved series all realistic at once.
    rng.shuffle(statuses)
    rng.shuffle(priorities)
    n = plan.tickets

    # Spread creation times across the scenario window. The first 40% of index
    # values are placed inside the last 14 days so the trend has real data;
    # the remainder reaches further back for aging and closed history. The
    # split is deterministic and independent of dict ordering.
    created_minutes: list[int] = []
    for i in range(n):
        if i % 5 in (0, 1):
            # Recent bucket: last 14 days, weighted towards the last few days.
            day = rng.randint(0, 13)
            minute = rng.randint(0, MINUTES_PER_DAY - 1)
            created_minutes.append(-(day * MINUTES_PER_DAY) - minute - 30)
        else:
            # Older bucket: 14-45 days ago for aging and closed history.
            day = rng.randint(14, SCENARIO_SPAN_DAYS - 1)
            minute = rng.randint(0, MINUTES_PER_DAY - 1)
            created_minutes.append(-(day * MINUTES_PER_DAY) - minute - 30)
    created_minutes.sort()  # oldest first; deterministic ordering

    # We must not assign active work to inactive agents.
    active_agents = [a for a in agents if a.is_active] or agents

    specs: list[dict] = []
    for i in range(n):
        status = statuses[i]
        priority = priorities[i]
        category = categories[(i * 5) % len(categories)]
        title, description = _TICKET_TEMPLATES[category][
            (i // len(categories)) % len(_TICKET_TEMPLATES[category])
        ]
        customer = customers[(i * 11) % len(customers)]
        created = created_minutes[i]
        age_minutes = -created

        active_status = status in (
            TicketStatus.OPEN,
            TicketStatus.IN_PROGRESS,
            TicketStatus.WAITING_ON_CUSTOMER,
        )
        # Unassigned is concentrated on *active* tickets so the unassigned
        # queue is realistic (~15-18% of active work), without leaving resolved
        # or closed tickets ownerless (which would look like unfinished work).
        # ~17% of active tickets: dense enough for a real queue, sparse enough
        # that most work has an owner.
        unassigned = ((i % 7 == 0) or (i % 23 == 0)) if active_status else False

        agent_key = None
        if not unassigned and active_agents:
            # Weighted, deterministic spread: earlier agents carry more load.
            agent_key = active_agents[(i * 7) % len(active_agents)].key

        # ``aging_over_7_days`` is defined against ``now`` (updated_at <= now -
        # 7 days), not against creation. So an old ticket only *ages* if its
        # last update is also old. Most older active tickets therefore get a
        # recent touch (someone looked at them), and a deliberate minority is
        # left genuinely stale. This keeps the aging count meaningful (~1 in 5
        # of the older active tickets) instead of flagging the whole backlog.
        if active_status and age_minutes > 7 * MINUTES_PER_DAY:
            if i % 5 == 0:
                # Genuinely stale: last touched shortly after creation.
                updated_offset = created + 30
            else:
                # Reviewed within the last week, but after creation and never
                # in the future.
                recent_touch = -rng.randint(0, 6 * MINUTES_PER_DAY)
                updated_offset = max(recent_touch, created + 30)
        else:
            updated_offset = created + min(age_minutes, 120)

        # Offset (minutes from creation) at which a resolved/closed ticket was
        # resolved; None for still-active tickets. Children (comments, history,
        # notifications) use this to stay causally ordered.
        resolved_offset = None
        if status in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
            span_cap = max(60, age_minutes - 30)
            resolved_offset = min(6 * 60 + (i % 48) * 60, span_cap)

        specs.append(
            {
                "key": f"ticket_{i:03d}",
                "index": i,
                "title": f"{title} (#{i + 1})",
                "description": description,
                "status": status,
                "priority": priority,
                "category": category,
                "customer_key": customer.key,
                "agent_key": agent_key,
                "created_at": created,
                "updated_at": updated_offset,
                "resolved_offset": resolved_offset,
                "age_minutes": age_minutes,
                "has_phone": i % 5 == 0,
                "at": created,
            }
        )
    return specs


def comment_specs(users: list[UserSpec], tickets: list[dict]) -> list[dict]:
    agents = _specs_by_role(users, Role.AGENT)
    admins = _specs_by_role(users, Role.ADMIN)
    specs: list[dict] = []
    for t in tickets:
        i = t["index"]
        at = t["created_at"] + 20
        # 1) Public customer reply.
        specs.append(
            {
                "key": f"comment_{i:03d}_c0",
                "ticket_key": t["key"],
                "author_key": t["customer_key"],
                "body": _CUSTOMER_COMMENTS[i % len(_CUSTOMER_COMMENTS)],
                "internal": False,
                "at": at,
            }
        )
        # 2) Public staff response (only when the ticket has an assignee).
        if t["agent_key"] is not None:
            specs.append(
                {
                    "key": f"comment_{i:03d}_c1",
                    "ticket_key": t["key"],
                    "author_key": t["agent_key"],
                    "body": _AGENT_COMMENTS[i % len(_AGENT_COMMENTS)],
                    "internal": False,
                    "at": at + 30,
                }
            )
        # 3) Resolution confirmation on resolved/closed tickets, placed just
        # before the resolution so the conversation ends coherently.
        if t.get("resolved_offset") is not None:
            specs.append(
                {
                    "key": f"comment_{i:03d}_resolved",
                    "ticket_key": t["key"],
                    "author_key": t["agent_key"],
                    "body": _RESOLUTION_COMMENTS[i % len(_RESOLUTION_COMMENTS)],
                    "internal": False,
                    "at": t["created_at"] + t["resolved_offset"] - 10,
                }
            )
        # 4) Staff-only internal note on some tickets (never a customer author).
        if i % 3 == 0:
            author = agents[(i * 7) % len(agents)].key if agents else admins[0].key
            specs.append(
                {
                    "key": f"comment_{i:03d}_c2",
                    "ticket_key": t["key"],
                    "author_key": author,
                    "body": _INTERNAL_NOTES[i % len(_INTERNAL_NOTES)],
                    "internal": True,
                    "at": at + 45,
                }
            )
    return specs


def history_specs(users: list[UserSpec], tickets: list[dict]) -> list[dict]:
    specs: list[dict] = []
    for t in tickets:
        i = t["index"]
        at = t["created_at"]
        # CREATED
        specs.append(
            {
                "key": f"hist_{i:03d}_created",
                "ticket_key": t["key"],
                "actor_key": t["customer_key"],
                "event_type": "TICKET_CREATED",
                "old_value": None,
                "new_value": {
                    "status": t["status"].value,
                    "priority": t["priority"].value,
                },
                "at": at,
            }
        )
        # ASSIGNED
        if t["agent_key"] is not None:
            specs.append(
                {
                    "key": f"hist_{i:03d}_assigned",
                    "ticket_key": t["key"],
                    "actor_key": "admin_00",
                    "event_type": "TICKET_ASSIGNED",
                    "old_value": None,
                    "new_value": {"assignee_user_id": t["agent_key"]},
                    "at": at + 5,
                }
            )
        # STATUS_CHANGED (any non-OPEN ticket)
        if t["status"] != TicketStatus.OPEN:
            specs.append(
                {
                    "key": f"hist_{i:03d}_status",
                    "ticket_key": t["key"],
                    "actor_key": t["agent_key"] or "admin_00",
                    "event_type": "STATUS_CHANGED",
                    "old_value": {"status": TicketStatus.OPEN.value},
                    "new_value": {"status": t["status"].value},
                    "at": at + 60,
                }
            )
        # PRIORITY_CHANGED (any non-NORMAL ticket)
        if t["priority"] != TicketPriority.NORMAL:
            specs.append(
                {
                    "key": f"hist_{i:03d}_priority",
                    "ticket_key": t["key"],
                    "actor_key": "admin_00",
                    "event_type": "PRIORITY_CHANGED",
                    "old_value": {"priority": TicketPriority.NORMAL.value},
                    "new_value": {"priority": t["priority"].value},
                    "at": at + 25,
                }
            )
    return specs


# Every ticket produces a single receipt notification, and only a subset
# produces the additional lifecycle notifications, so the panel is populated
# without one ticket generating six rows. Roughly 2 notifications per ticket.
_EXTRA_NOTIFICATION_STRIDE = 7


def notification_specs(
    users: list[UserSpec],
    tickets: list[dict],
    conversations: list[dict] | None = None,
    requests: list[dict] | None = None,
) -> list[dict]:
    specs: list[dict] = []
    for t in tickets:
        i = t["index"]
        at = t["created_at"] + 10
        number = "{number}"
        extra = i % _EXTRA_NOTIFICATION_STRIDE == 0
        # Assignment notification to the assignee.
        if extra and t["agent_key"] is not None:
            specs.append(
                {
                    "key": f"notif_{i:03d}_assigned",
                    "recipient_key": t["agent_key"],
                    "ticket_key": t["key"],
                    "type": NotificationType.TICKET_ASSIGNED,
                    "title": f"Ticket #{number} assigned to you",
                    "message": f"Ticket #{number} has been assigned to you.",
                    "is_read": i % 4 == 0,
                    "at": at,
                }
            )
        # Status change notification to the customer.
        if extra and t["status"] != TicketStatus.OPEN:
            specs.append(
                {
                    "key": f"notif_{i:03d}_status",
                    "recipient_key": t["customer_key"],
                    "ticket_key": t["key"],
                    "type": NotificationType.STATUS_CHANGED,
                    "title": f"Ticket #{number} is now {t['status'].value}",
                    "message": f"Your ticket #{number} moved to {t['status'].value}.",
                    "is_read": i % 3 == 0,
                    "at": at + 40,
                }
            )
        # New-comment notification to the customer on some tickets.
        if extra and t["agent_key"] is not None:
            specs.append(
                {
                    "key": f"notif_{i:03d}_comment",
                    "recipient_key": t["customer_key"],
                    "ticket_key": t["key"],
                    "type": NotificationType.NEW_COMMENT,
                    "title": f"New reply on ticket #{number}",
                    "message": f"There is a new reply on your ticket #{number}.",
                    "is_read": i % 5 == 0,
                    "at": at + 55,
                }
            )
        # Customer reply notification to the assigned agent on some tickets.
        if extra and t["agent_key"] is not None:
            specs.append(
                {
                    "key": f"notif_{i:03d}_customer_reply",
                    "recipient_key": t["agent_key"],
                    "ticket_key": t["key"],
                    "type": NotificationType.NEW_COMMENT,
                    "title": f"New reply on ticket #{number}",
                    "message": f"The customer replied to ticket #{number}.",
                    "is_read": i % 3 == 0,
                    "at": at + 25,
                }
            )
        # Needs-assignment notification to an admin for unassigned tickets.
        if t["agent_key"] is None:
            specs.append(
                {
                    "key": f"notif_{i:03d}_needs",
                    "recipient_key": "admin_00",
                    "ticket_key": t["key"],
                    "type": NotificationType.TICKET_NEEDS_ASSIGNMENT,
                    "title": f"Ticket #{number} needs an assignee",
                    "message": f"Ticket #{number} could not be auto-assigned.",
                    "is_read": False,
                    "at": at,
                }
            )
        # Customer receipt for every ticket.
        specs.append(
            {
                "key": f"notif_{i:03d}_created",
                "recipient_key": t["customer_key"],
                "ticket_key": t["key"],
                "type": NotificationType.TICKET_CREATED,
                "title": "Your ticket was received",
                "message": (f"We received ticket #{number} and it is being reviewed."),
                "is_read": True,
                "at": at - 5,
            }
        )
        # Feedback request for resolved tickets that have no answer yet.
        if t["status"] == TicketStatus.RESOLVED and not _ticket_has_feedback(i):
            specs.append(
                {
                    "key": f"notif_{i:03d}_feedback",
                    "recipient_key": t["customer_key"],
                    "ticket_key": t["key"],
                    "type": NotificationType.TICKET_RESOLVED,
                    "title": "Your ticket has been resolved",
                    "message": (
                        f"Ticket #{number} was resolved. Share your feedback "
                        "to let us know how we did."
                    ),
                    "is_read": i % 2 == 0,
                    "at": at + 90,
                }
            )

    # Employee <-> Owner private threads: one notification per message, for the
    # recipient of that message (never the sender). Read state mirrors the
    # message's own read_at so both inboxes agree.
    if conversations:
        # The preserved Owner is not part of ``demo_users()``; the sentinel is
        # resolved to the real OWNER row by the seeder.
        owner_key = "__owner__"
        for conversation in conversations:
            for n in range(3):
                staff_sender = n % 2 == 0
                specs.append(
                    {
                        "key": f"notif_{conversation['key']}_msg_{n}",
                        "recipient_key": (
                            owner_key if staff_sender else conversation["staff_key"]
                        ),
                        "conversation_key": conversation["key"],
                        "type": (
                            NotificationType.STAFF_MESSAGE_RECEIVED
                            if staff_sender
                            else NotificationType.OWNER_MESSAGE_RECEIVED
                        ),
                        "title": (
                            "New private message from a staff member"
                            if staff_sender
                            else "The Owner replied to you"
                        ),
                        "message": (
                            "A staff member sent you a private message."
                            if staff_sender
                            else "The Owner sent you a private message."
                        ),
                        "is_read": _staff_message_read(conversation, n),
                        "at": conversation["created_at"] + n * 45,
                    }
                )

    # Account-management requests: reviewers hear about a new request, and the
    # requester hears when it is decided. Never the actor.
    if requests:
        admins = _specs_by_role(users, Role.ADMIN)
        for request in requests:
            index = int(request["key"].rsplit("_", 1)[1])
            reviewer = next(
                admin for admin in admins if admin.key != request["created_by_key"]
            )
            specs.append(
                {
                    "key": f"notif_{request['key']}_created",
                    "recipient_key": reviewer.key,
                    "request_key": request["key"],
                    "type": NotificationType.ESCALATION_CREATED,
                    "title": "New account request",
                    "message": "An account-management request needs review.",
                    "is_read": index % 3 == 0,
                    "at": request["at"] + 2,
                }
            )
            if request["status"] != EscalationStatus.PENDING:
                specs.append(
                    {
                        "key": f"notif_{request['key']}_updated",
                        "recipient_key": request["created_by_key"],
                        "request_key": request["key"],
                        "type": NotificationType.ESCALATION_UPDATED,
                        "title": "Your account request was updated",
                        "message": (
                            "Your account-management request is now "
                            f"{request['status'].value}."
                        ),
                        "is_read": index % 2 == 0,
                        "at": request["at"] + 130,
                    }
                )
    return specs


def _ticket_has_feedback(index: int) -> bool:
    """Deterministic split of resolved tickets into answered / awaiting."""
    return index % 3 == 0


_FEEDBACK_COMMENTS = [
    "The agent explained every step and kept me updated the whole time.",
    "Resolved quickly, though the first response took a little while.",
    "Clear and friendly support; the workaround solved my problem.",
    "Issue is fixed. A summary of the root cause would have helped.",
]

_INTERNAL_SUBJECTS = [
    "Quarterly support update",
    "New triage guideline for urgent tickets",
    "Reminder: handover notes before the rotation",
    "Recognition for last week's outage response",
    "Please review the updated escalation policy",
    "Coverage plan for the upcoming holiday",
]

_INTERNAL_BODIES = [
    "Thanks for the steady work this quarter. Reply here if anything is "
    "unclear about the new targets.",
    "Urgent tickets now need an owner within the first hour. Ping me if the "
    "queue looks thin during your shift.",
    "Please leave short handover notes before you log off so the next shift "
    "can pick up without asking around.",
    "Great job keeping customers informed during the outage. This is exactly "
    "the standard we want to hold.",
    "The escalation policy was clarified this week; the summary is in the "
    "shared handbook.",
    "Here is the coverage plan for the holiday period. Swap directly with a "
    "colleague if the dates do not work for you.",
]


def internal_message_specs(users: list[UserSpec]) -> list[dict]:
    """Deterministic Owner-composed internal messages (broadcasts + notes).

    Each spec lists its recipient keys explicitly so the per-recipient read
    split is reproducible and the notification rows can be tied to real
    recipient rows.
    """
    agents = _specs_by_role(users, Role.AGENT)
    admins = _specs_by_role(users, Role.ADMIN)
    everyone = [*agents, *admins]
    groups: list[tuple[InternalAudience, list[str]]] = [
        (InternalAudience.EVERYONE, [u.key for u in everyone]),
        (InternalAudience.AGENTS, [u.key for u in agents]),
        (InternalAudience.ADMINS, [u.key for u in admins]),
        (InternalAudience.INDIVIDUAL, [agents[0].key]),
        (InternalAudience.INDIVIDUAL, [admins[0].key]),
        (InternalAudience.AGENTS, [u.key for u in agents[:4]]),
    ]
    specs: list[dict] = []
    for i, (audience, keys) in enumerate(groups):
        specs.append(
            {
                "key": f"internal_{i:02d}",
                "audience": audience,
                "subject": _INTERNAL_SUBJECTS[i % len(_INTERNAL_SUBJECTS)],
                "body": _INTERNAL_BODIES[i % len(_INTERNAL_BODIES)],
                "recipient_keys": keys,
                # Determines a stable per-recipient read/unread split.
                "read_stride": (i % 3) + 1,
                "at": 200 + i * 30,
            }
        )
    return specs


def feedback_specs(tickets: list[dict]) -> list[dict]:
    """Feedback for the deterministic subset of resolved tickets that answered."""
    specs: list[dict] = []
    for t in tickets:
        if t["status"] != TicketStatus.RESOLVED or not _ticket_has_feedback(t["index"]):
            continue
        specs.append(
            {
                "key": f"feedback_{t['index']:03d}",
                "ticket_key": t["key"],
                "customer_key": t["customer_key"],
                "rating": 2 + (t["index"] % 4),
                "comment": _FEEDBACK_COMMENTS[t["index"] % len(_FEEDBACK_COMMENTS)],
                "at": t["created_at"] + 120,
            }
        )
    return specs


def attachment_specs(tickets: list[dict]) -> list[dict]:
    selected = [t for t in tickets if t["index"] % 10 == 0][:N_ATTACHMENTS]
    specs: list[dict] = []
    for n, t in enumerate(selected):
        is_text = n % 2 == 0
        if is_text:
            filename = f"diagnostics-{t['index']:03d}.txt"
            content_type = "text/plain"
            content = (
                f"Diagnostic log captured for ticket #{t['index'] + 1}\n"
                "----------------------------------------------\n"
                f"status={t['status'].value} priority={t['priority'].value}\n"
                "No sensitive data is present in this synthetic demo file.\n"
            ).encode()
        else:
            filename = f"screenshot-{t['index']:03d}.png"
            content_type = "image/png"
            # A tiny valid 1x1 PNG (synthetic placeholder, not real content).
            content = bytes.fromhex(
                "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
                "890000000d49444154789c6360000002000100ffff03000006000557bfabd400"
                "00000049454e44ae426082"
            )
        specs.append(
            {
                "key": f"attachment_{t['index']:03d}",
                "ticket_key": t["key"],
                "uploader_key": t["customer_key"],
                "filename": filename,
                "content_type": content_type,
                "content": content,
                "at": t["created_at"] + 15,
            }
        )
    return specs


def staff_conversation_specs(users: list[UserSpec]) -> list[dict]:
    agents = _specs_by_role(users, Role.AGENT)
    admins = _specs_by_role(users, Role.ADMIN)
    staff = [*agents, *admins]
    participants = staff[:N_STAFF_CONVERSATIONS]
    specs: list[dict] = []
    for i, member in enumerate(participants):
        specs.append(
            {
                "key": f"conversation_{i:02d}",
                "staff_key": member.key,
                "subject": _STAFF_SUBJECTS[i % len(_STAFF_SUBJECTS)],
                "created_at": 60 + i * 90,
            }
        )
    return specs


def staff_message_specs(conversations: list[dict]) -> list[dict]:
    specs: list[dict] = []
    for c in conversations:
        base = c["created_at"]
        for n in range(3):
            # Alternate staff/owner senders.
            sender_is_staff = n % 2 == 0
            specs.append(
                {
                    "key": f"{c['key']}_msg_{n}",
                    "conversation_key": c["key"],
                    "sender": "staff" if sender_is_staff else "owner",
                    "staff_key": c["staff_key"],
                    "body": _STAFF_MESSAGES[
                        (n + conversation_index(c)) % len(_STAFF_MESSAGES)
                    ],
                    "at": base + n * 45,
                    "read": _staff_message_read(c, n),
                }
            )
    return specs


def _staff_message_read(conversation: dict, n: int) -> bool:
    """Deterministic read mix in both directions, for demo read/unread states.

    The matching notification reuses this value, so the message's own read
    state and the notification's read state never disagree in demo data.
    """
    index = conversation_index(conversation)
    if n == 0:
        return index % 3 != 0
    if n == 1:
        return index % 4 != 0
    return False


def conversation_index(conversation: dict) -> int:
    key = conversation["key"]
    try:
        return int(key.rsplit("_", 1)[1])
    except (IndexError, ValueError):
        return 0


def account_request_specs(users: list[UserSpec]) -> list[dict]:
    agents = _specs_by_role(users, Role.AGENT)
    admins = _specs_by_role(users, Role.ADMIN)
    customers = _specs_by_role(users, Role.CUSTOMER)
    creators = [*agents[:6], *admins[:6]]
    statuses = [
        EscalationStatus.PENDING,
        EscalationStatus.IN_REVIEW,
        EscalationStatus.APPROVED,
        EscalationStatus.REJECTED,
        EscalationStatus.COMPLETED,
    ]
    categories = list(EscalationCategory)
    specs: list[dict] = []
    for i in range(N_ACCOUNT_REQUESTS):
        # Weight so several requests remain in early workflow states.
        status = statuses[i % len(statuses)]
        target = customers[(i * 13) % len(customers)]
        specs.append(
            {
                "key": f"request_{i:02d}",
                "created_by_key": creators[i % len(creators)].key,
                "target_key": target.key,
                "category": categories[i % len(categories)],
                "justification": _ESCALATION_JUSTIFICATION[
                    i % len(_ESCALATION_JUSTIFICATION)
                ],
                "internal_details": (
                    "Verified via support ticket history; no identity change "
                    "requested here."
                    if i % 2 == 0
                    else None
                ),
                "status": status,
                "at": 120 + i * 240,
            }
        )
    return specs


def account_request_comment_specs(requests: list[dict]) -> list[dict]:
    specs: list[dict] = []
    for r in requests:
        specs.append(
            {
                "key": f"{r['key']}_comment_0",
                "request_key": r["key"],
                "author_key": r["created_by_key"],
                "body": "Adding context: this blocks the customer from working today.",
                "at": r["at"] + 30,
            }
        )
        if r["status"] != EscalationStatus.PENDING:
            specs.append(
                {
                    "key": f"{r['key']}_comment_1",
                    "request_key": r["key"],
                    "author_key": "admin_00",
                    "body": "Reviewed against the policy; see the decision note.",
                    "at": r["at"] + 90,
                }
            )
    return specs


# --------------------------------------------------------------------------- #
# Seeding
# --------------------------------------------------------------------------- #


@dataclass
class Counts:
    inserted: int = 0
    reused: int = 0
    conflicts: int = 0
    failed: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "inserted": self.inserted,
            "reused": self.reused,
            "skipped_conflicts": self.conflicts,
            "failed": self.failed,
        }


@dataclass
class SeedResult:
    counts: dict[str, dict[str, int]] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)
    owner_before: dict | None = None
    owner_after: dict | None = None
    expected: dict[str, int] = field(default_factory=dict)
    upload_root: str = ""

    def as_dict(self) -> dict:
        return {
            "marker": MARKER,
            "upload_root": self.upload_root,
            "counts": self.counts,
            "conflicts": self.conflicts,
            "owner_unchanged": self.owner_before == self.owner_after,
            "expected": self.expected,
        }


async def _owner_row(session) -> dict | None:
    owner = (await session.exec(select(User).where(User.role == Role.OWNER))).first()
    if owner is None:
        return None
    raw = {
        "id": str(owner.id),
        "clerk_id": owner.clerk_id,
        "full_name": owner.full_name,
        "username": owner.username,
        "email": owner.email,
        "role": owner.role.value,
        "is_active": owner.is_active,
        "created_at": owner.created_at.isoformat(),
        "updated_at": owner.updated_at.isoformat(),
    }
    raw["hash"] = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
    return raw


async def _seed_users(session) -> tuple[dict[str, User], Counts, list[str]]:
    counts = Counts()
    users: dict[str, User] = {}
    collisions: list[str] = []
    specs = demo_users()
    usernames = [s.username for s in specs]
    emails = [s.email for s in specs]
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
        expected_id = _uid("user", spec.key)
        existing = by_username.get(spec.username) or by_email.get(spec.email)
        if existing is not None:
            if existing.id == expected_id:
                counts.reused += 1
                users[spec.key] = existing
            else:
                counts.conflicts += 1
                collisions.append(
                    f"user {spec.username} exists with a different id "
                    f"({existing.id}); refusing to overwrite"
                )
            continue
        user = User(
            id=expected_id,
            clerk_id=None,
            full_name=spec.full_name,
            username=spec.username,
            email=spec.email,
            password_hash=None,
            role=spec.role,
            is_active=spec.is_active,
            created_at=_at(0),
            updated_at=_at(0),
        )
        session.add(user)
        counts.inserted += 1
        users[spec.key] = user

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
        created = _at(spec["created_at"])
        # A ticket can only be resolved after it was created; resolution is
        # placed somewhere in the window between creation and now, then the
        # updated timestamp follows it. This keeps created <= assigned <=
        # resolved <= now for every row.
        resolved = None
        if spec["resolved_offset"] is not None:
            resolved = created + timedelta(minutes=spec["resolved_offset"])
        updated = _at(spec["updated_at"])
        if resolved is not None:
            updated = max(updated, resolved)
        # Never let an update land in the future.
        updated = min(updated, active_plan().anchor)
        ticket = Ticket(
            id=ticket_id,
            ticket_number=number,
            title=spec["title"],
            description=spec["description"],
            status=spec["status"],
            priority=spec["priority"],
            category=spec["category"],
            contact_phone=(
                f"+1-555-01{spec['index']:02d}" if spec["has_phone"] else None
            ),
            created_by_user_id=users[spec["customer_key"]].id,
            assignee_user_id=agent.id if agent else None,
            assigned_at=(created + timedelta(minutes=5)) if agent else None,
            created_at=created,
            updated_at=updated,
            resolved_at=resolved,
        )
        session.add(ticket)
        counts.inserted += 1
        result[spec["key"]] = ticket
    await session.flush()
    return result, counts, collisions


async def _seed_comments(session, users, tickets_map) -> Counts:
    counts = Counts()
    specs = comment_specs(demo_users(), ticket_specs(demo_users()))
    expected_ids = [_uid("comment", s["key"]) for s in specs]
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
    return counts


async def _seed_history(session, users, tickets_map) -> Counts:
    counts = Counts()
    specs = history_specs(demo_users(), ticket_specs(demo_users()))
    expected_ids = [_uid("history", s["key"]) for s in specs]
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
        new_value = spec["new_value"]
        if (
            isinstance(new_value, dict)
            and spec["event_type"] == "TICKET_ASSIGNED"
            and "assignee_user_id" in new_value
        ):
            new_value = {
                "assignee_user_id": str(users[new_value["assignee_user_id"]].id)
            }
        session.add(
            TicketHistory(
                id=expected_id,
                ticket_id=tickets_map[spec["ticket_key"]].id,
                actor_user_id=users[spec["actor_key"]].id,
                event_type=spec["event_type"],
                old_value=spec["old_value"],
                new_value=new_value,
                created_at=_at(spec["at"]),
            )
        )
        counts.inserted += 1
    return counts


async def _seed_notifications(session, users, tickets_map) -> Counts:
    counts = Counts()
    user_specs = demo_users()
    specs = notification_specs(
        user_specs,
        ticket_specs(user_specs),
        conversations=staff_conversation_specs(user_specs),
        requests=account_request_specs(user_specs),
    )
    expected_ids = [_uid("notification", s["key"]) for s in specs]
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
        if spec["recipient_key"] == "__owner__":
            owner = (
                await session.exec(select(User).where(User.role == Role.OWNER))
            ).first()
            if owner is None:
                raise SeedRefused(
                    "Cannot seed owner notifications without an OWNER row."
                )
            recipient_user_id = owner.id
        else:
            recipient_user_id = users[spec["recipient_key"]].id
        ticket = tickets_map.get(spec["ticket_key"]) if spec.get("ticket_key") else None
        number = ticket.ticket_number if ticket is not None else None

        def _fill(text: str, *, number=number) -> str:
            return text.replace("{number}", str(number)) if number is not None else text

        session.add(
            Notification(
                id=expected_id,
                recipient_user_id=recipient_user_id,
                related_ticket_id=ticket.id if ticket is not None else None,
                related_conversation_id=(
                    _uid("conversation", spec["conversation_key"])
                    if spec.get("conversation_key")
                    else None
                ),
                related_account_request_id=(
                    _uid("request", spec["request_key"])
                    if spec.get("request_key")
                    else None
                ),
                type=spec["type"],
                title=_fill(spec["title"]),
                message=_fill(spec["message"])[:500],
                is_read=spec["is_read"],
                created_at=_at(spec["at"]),
            )
        )
        counts.inserted += 1
    return counts


async def _seed_internal_messages(session, users, owner) -> Counts:
    """Owner-composed internal messages, their recipients, and notifications.

    Each recipient row carries an identity snapshot and a deterministic read
    state; the matching notification's read state is derived from it, so the
    two never disagree in the demo dataset.
    """
    counts = Counts()
    specs = internal_message_specs(demo_users())
    message_ids = [_uid("internal_message", s["key"]) for s in specs]
    existing = set(
        (
            await session.exec(
                select(InternalMessage.id).where(InternalMessage.id.in_(message_ids))
            )
        ).all()
    )
    for spec in specs:
        message_id = _uid("internal_message", spec["key"])
        if message_id in existing:
            counts.reused += 1
            continue
        created = _at(spec["at"])
        session.add(
            InternalMessage(
                id=message_id,
                sender_user_id=owner.id,
                audience=spec["audience"],
                subject=spec["subject"],
                body=spec["body"],
                recipient_count=len(spec["recipient_keys"]),
                created_at=created,
            )
        )
        for index, recipient_key in enumerate(spec["recipient_keys"]):
            recipient = users[recipient_key]
            read_at = (
                created + timedelta(minutes=5)
                if index % spec["read_stride"] == 0
                else None
            )
            session.add(
                InternalMessageRecipient(
                    id=_uid("internal_recipient", f"{spec['key']}:{recipient_key}"),
                    message_id=message_id,
                    recipient_user_id=recipient.id,
                    recipient_role_snapshot=recipient.role,
                    recipient_full_name_snapshot=recipient.full_name,
                    recipient_email_snapshot=recipient.email,
                    created_at=created,
                    read_at=read_at,
                )
            )
            session.add(
                Notification(
                    id=_uid("notification", f"internal:{spec['key']}:{recipient_key}"),
                    recipient_user_id=recipient.id,
                    related_internal_message_id=message_id,
                    type=NotificationType.INTERNAL_MESSAGE_RECEIVED,
                    title="New message from the Owner",
                    message=(
                        "The Owner sent you an internal message. Open it to "
                        "read the details."
                    ),
                    is_read=read_at is not None,
                    created_at=created,
                )
            )
        counts.inserted += 1
    return counts


async def _seed_feedback(session, users, tickets_map) -> Counts:
    counts = Counts()
    specs = feedback_specs(ticket_specs(demo_users()))
    expected_ids = [_uid("feedback", s["key"]) for s in specs]
    existing = set(
        (
            await session.exec(
                select(TicketFeedback.id).where(TicketFeedback.id.in_(expected_ids))
            )
        ).all()
    )
    for spec in specs:
        expected_id = _uid("feedback", spec["key"])
        if expected_id in existing:
            counts.reused += 1
            continue
        session.add(
            TicketFeedback(
                id=expected_id,
                ticket_id=tickets_map[spec["ticket_key"]].id,
                customer_user_id=users[spec["customer_key"]].id,
                rating=spec["rating"],
                comment=spec["comment"],
                created_at=_at(spec["at"]),
            )
        )
        counts.inserted += 1
    return counts


async def _seed_attachments(
    session, users, tickets_map, upload_root: Path
) -> tuple[Counts, list[Path]]:
    counts = Counts()
    written: list[Path] = []
    upload_root.mkdir(parents=True, exist_ok=True)
    specs = attachment_specs(ticket_specs(demo_users()))
    expected_ids = [_uid("attachment", s["key"]) for s in specs]
    existing = set(
        (
            await session.exec(
                select(Attachment.id).where(Attachment.id.in_(expected_ids))
            )
        ).all()
    )
    for spec in specs:
        expected_id = _uid("attachment", spec["key"])
        storage_key = f"demo-{expected_id.hex[:12]}-{spec['filename']}"
        destination = upload_root / storage_key
        if expected_id in existing:
            counts.reused += 1
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
                scan_status=AttachmentScanStatus.CLEAN,
                created_at=_at(spec["at"]),
            )
        )
        destination.write_bytes(spec["content"])
        written.append(destination)
        counts.inserted += 1
    return counts, written


async def _seed_staff_conversations(
    session, users: dict[str, User], owner: User
) -> tuple[dict[str, StaffConversation], Counts]:
    counts = Counts()
    result: dict[str, StaffConversation] = {}
    specs = staff_conversation_specs(demo_users())
    expected_ids = [_uid("conversation", s["key"]) for s in specs]
    existing_rows = (
        await session.exec(
            select(StaffConversation).where(StaffConversation.id.in_(expected_ids))
        )
    ).all()
    existing_by_id = {row.id: row for row in existing_rows}
    for spec in specs:
        cid = _uid("conversation", spec["key"])
        if cid in existing_by_id:
            counts.reused += 1
            result[spec["key"]] = existing_by_id[cid]
            continue
        conversation = StaffConversation(
            id=cid,
            staff_user_id=users[spec["staff_key"]].id,
            owner_user_id=owner.id,
            subject=spec["subject"],
            created_at=_at(spec["created_at"]),
            updated_at=_at(spec["created_at"]),
            last_message_at=_at(spec["created_at"] + 90),
        )
        session.add(conversation)
        counts.inserted += 1
        result[spec["key"]] = conversation
    await session.flush()
    return result, counts


async def _seed_staff_messages(
    session, users: dict[str, User], owner: User, conversations_map
) -> Counts:
    counts = Counts()
    specs = staff_message_specs(staff_conversation_specs(demo_users()))
    expected_ids = [_uid("staff_message", s["key"]) for s in specs]
    existing = set(
        (
            await session.exec(
                select(StaffMessage.id).where(StaffMessage.id.in_(expected_ids))
            )
        ).all()
    )
    for spec in specs:
        expected_id = _uid("staff_message", spec["key"])
        if expected_id in existing:
            counts.reused += 1
            continue
        sender_id = (
            users[spec["staff_key"]].id if spec["sender"] == "staff" else owner.id
        )
        session.add(
            StaffMessage(
                id=expected_id,
                conversation_id=conversations_map[spec["conversation_key"]].id,
                sender_user_id=sender_id,
                body=spec["body"],
                created_at=_at(spec["at"]),
                read_at=_at(spec["at"] + 10) if spec["read"] else None,
            )
        )
        counts.inserted += 1
    return counts


async def _seed_account_requests(
    session, users: dict[str, User], tickets_map
) -> tuple[dict[str, AccountManagementRequest], Counts]:
    counts = Counts()
    result: dict[str, AccountManagementRequest] = {}
    specs = account_request_specs(demo_users())
    expected_ids = [_uid("request", s["key"]) for s in specs]
    existing_rows = (
        await session.exec(
            select(AccountManagementRequest).where(
                AccountManagementRequest.id.in_(expected_ids)
            )
        )
    ).all()
    existing_by_id = {row.id: row for row in existing_rows}
    decided = {
        EscalationStatus.APPROVED,
        EscalationStatus.REJECTED,
        EscalationStatus.COMPLETED,
    }
    for spec in specs:
        rid = _uid("request", spec["key"])
        if rid in existing_by_id:
            counts.reused += 1
            result[spec["key"]] = existing_by_id[rid]
            continue
        target = users[spec["target_key"]]
        status = spec["status"]
        is_decided = status in decided
        is_completed = status == EscalationStatus.COMPLETED
        request = AccountManagementRequest(
            id=rid,
            target_user_id=target.id,
            target_full_name_snapshot=target.full_name,
            target_email_snapshot=target.email,
            ticket_id=None,
            category=spec["category"],
            justification=spec["justification"],
            internal_details=spec["internal_details"],
            status=status,
            decision_reason=(
                "Approved per the account-recovery policy."
                if status == EscalationStatus.APPROVED
                else "Rejected: identity could not be verified."
                if status == EscalationStatus.REJECTED
                else "Completed after the change was applied."
                if status == EscalationStatus.COMPLETED
                else None
            ),
            decided_by_user_id=users["admin_00"].id if is_decided else None,
            decided_at=_at(spec["at"] + 120) if is_decided else None,
            completed_by_user_id=users["admin_00"].id if is_completed else None,
            completed_at=_at(spec["at"] + 240) if is_completed else None,
            created_by_user_id=users[spec["created_by_key"]].id,
            created_at=_at(spec["at"]),
            updated_at=_at(spec["at"] + 240),
        )
        session.add(request)
        counts.inserted += 1
        result[spec["key"]] = request
    await session.flush()
    return result, counts


async def _seed_account_request_children(
    session, users, requests_map
) -> tuple[Counts, Counts]:
    comment_counts = Counts()
    event_counts = Counts()

    comments = account_request_comment_specs(account_request_specs(demo_users()))
    cids = [_uid("request_comment", s["key"]) for s in comments]
    existing_c = set(
        (
            await session.exec(
                select(AccountRequestComment.id).where(
                    AccountRequestComment.id.in_(cids)
                )
            )
        ).all()
    )
    for spec in comments:
        cid = _uid("request_comment", spec["key"])
        if cid in existing_c:
            comment_counts.reused += 1
            continue
        session.add(
            AccountRequestComment(
                id=cid,
                request_id=requests_map[spec["request_key"]].id,
                author_user_id=users[spec["author_key"]].id,
                body=spec["body"],
                created_at=_at(spec["at"]),
            )
        )
        comment_counts.inserted += 1

    # One CREATED event plus a decision event for decided requests.
    specs = account_request_specs(demo_users())
    events: list[dict] = []
    for spec in specs:
        events.append(
            {
                "key": f"{spec['key']}_ev_created",
                "request_key": spec["key"],
                "actor_key": spec["created_by_key"],
                "event_type": "REQUEST_CREATED",
                "old_value": None,
                "new_value": {"status": EscalationStatus.PENDING.value},
                "at": spec["at"],
            }
        )
        if spec["status"] != EscalationStatus.PENDING:
            events.append(
                {
                    "key": f"{spec['key']}_ev_status",
                    "request_key": spec["key"],
                    "actor_key": "admin_00",
                    "event_type": "STATUS_CHANGED",
                    "old_value": {"status": EscalationStatus.PENDING.value},
                    "new_value": {"status": spec["status"].value},
                    "at": spec["at"] + 120,
                }
            )
    eids = [_uid("request_event", s["key"]) for s in events]
    existing_e = set(
        (
            await session.exec(
                select(AccountRequestEvent.id).where(AccountRequestEvent.id.in_(eids))
            )
        ).all()
    )
    for spec in events:
        eid = _uid("request_event", spec["key"])
        if eid in existing_e:
            event_counts.reused += 1
            continue
        session.add(
            AccountRequestEvent(
                id=eid,
                request_id=requests_map[spec["request_key"]].id,
                actor_user_id=users[spec["actor_key"]].id,
                event_type=spec["event_type"],
                old_value=spec["old_value"],
                new_value=spec["new_value"],
                created_at=_at(spec["at"]),
            )
        )
        event_counts.inserted += 1
    return comment_counts, event_counts


def expected_counts(plan: DemoPlan, tickets: list[dict] | None = None) -> dict:
    """The exact row counts this plan will produce (pure, no database).

    Used both by the dry-run report and by the post-seed verification, so the
    two can never disagree.
    """
    tickets = tickets if tickets is not None else ticket_specs(demo_users())
    users = demo_users()
    conversations = staff_conversation_specs(users)
    requests = account_request_specs(users)
    return {
        "size": plan.size,
        "users_total": plan.users_total,
        "owners": 1,
        "admins": plan.admins,
        "agents": plan.agents,
        "customers": plan.customers,
        "inactive_customers": sum(
            1 for u in users if u.role == Role.CUSTOMER and not u.is_active
        ),
        "inactive_agents": sum(
            1 for u in users if u.role == Role.AGENT and not u.is_active
        ),
        "tickets": len(tickets),
        "tickets_by_status": {
            status.value: sum(1 for t in tickets if t["status"] == status)
            for status in TicketStatus
        },
        "tickets_by_priority": {
            priority.value: sum(1 for t in tickets if t["priority"] == priority)
            for priority in TicketPriority
        },
        "comments": len(comment_specs(users, tickets)),
        "internal_notes": sum(
            1 for c in comment_specs(users, tickets) if c["internal"]
        ),
        "history": len(history_specs(users, tickets)),
        "notifications": len(
            notification_specs(
                users,
                tickets,
                conversations=conversations,
                requests=requests,
            )
        ),
        "attachments": len(attachment_specs(tickets)),
        "staff_conversations": len(conversations),
        "staff_messages": len(staff_message_specs(conversations)),
        "account_requests": len(requests),
        "feedback": len(feedback_specs(tickets)),
        "internal_messages": len(internal_message_specs(users)),
    }


def dry_run_report(plan: DemoPlan) -> dict:
    """Describe exactly what a seed would insert, without touching a database.

    This performs no I/O beyond building the pure spec lists, so it is safe to
    run against production configuration. It is the artefact an operator reads
    before approving a write.
    """
    tickets = ticket_specs(demo_users())
    active = [
        t
        for t in tickets
        if t["status"]
        in (
            TicketStatus.OPEN,
            TicketStatus.IN_PROGRESS,
            TicketStatus.WAITING_ON_CUSTOMER,
        )
    ]
    unassigned_active = [t for t in active if t["agent_key"] is None]
    urgent_active = [t for t in active if t["priority"] == TicketPriority.URGENT]
    now = plan.anchor
    recent = [t for t in tickets if t["created_at"] >= -14 * MINUTES_PER_DAY]
    aging = [t for t in active if t["updated_at"] <= -7 * MINUTES_PER_DAY]
    unassigned_over_24h = [
        t for t in unassigned_active if t["created_at"] <= -MINUTES_PER_DAY
    ]
    return {
        "marker": MARKER,
        "dry_run": True,
        "anchor": now.isoformat(),
        "expected": expected_counts(plan, tickets),
        "derived": {
            "active_tickets": len(active),
            "unassigned_active": len(unassigned_active),
            "unassigned_active_pct": (
                round(100 * len(unassigned_active) / len(active)) if active else 0
            ),
            "urgent_active": len(urgent_active),
            "created_in_last_14_days": len(recent),
            "aging_over_7_days": len(aging),
            "unassigned_over_24h": len(unassigned_over_24h),
        },
    }


async def seed(upload_root: Path, *, session_factory=None) -> SeedResult:
    """Insert the deterministic demo dataset (idempotent).

    ``session_factory`` defaults to the application session factory; the tests
    inject a factory bound to a disposable database so the real seed logic can
    be exercised without ever touching the configured target.
    """
    factory = session_factory or async_session
    plan = active_plan()
    tickets = ticket_specs(demo_users())
    result = SeedResult(upload_root=str(upload_root))
    result.expected = expected_counts(plan, tickets)

    created_files: list[Path] = []
    async with factory() as session:
        owner_before = await _owner_row(session)
        if owner_before is None:
            raise SeedRefused(
                "No OWNER row found in the target database; refusing to seed. "
                "Restore the Owner first."
            )
        result.owner_before = owner_before
        owner = (
            await session.exec(select(User).where(User.role == Role.OWNER))
        ).first()

        # Serialize ticket-number allocation against concurrent app writers.
        bind = session.get_bind()
        if bind is not None and bind.dialect.name == "postgresql":
            await session.exec(
                text("SELECT pg_advisory_xact_lock(:key)"),
                params={"key": 20261019},
            )

        try:
            users, users_counts, user_collisions = await _seed_users(session)
            result.counts["users"] = users_counts.as_dict()
            result.conflicts.extend(user_collisions)

            missing = [s.key for s in demo_users() if s.key not in users]
            if missing or user_collisions:
                raise SeedRefused(
                    "Refusing to seed: required demo users could not be created "
                    f"({len(missing)} unresolved). Conflicts: {user_collisions}"
                )

            tickets_map, ticket_counts, ticket_collisions = await _seed_tickets(
                session, users, tickets
            )
            result.counts["tickets"] = ticket_counts.as_dict()
            result.conflicts.extend(ticket_collisions)

            result.counts["comments"] = (
                await _seed_comments(session, users, tickets_map)
            ).as_dict()
            result.counts["history"] = (
                await _seed_history(session, users, tickets_map)
            ).as_dict()
            result.counts["feedback"] = (
                await _seed_feedback(session, users, tickets_map)
            ).as_dict()
            result.counts["internal_messages"] = (
                await _seed_internal_messages(session, users, owner)
            ).as_dict()
            attach_counts, created_files = await _seed_attachments(
                session, users, tickets_map, upload_root
            )
            result.counts["attachments"] = attach_counts.as_dict()

            conv_map, conv_counts = await _seed_staff_conversations(
                session, users, owner
            )
            result.counts["staff_conversations"] = conv_counts.as_dict()
            result.counts["staff_messages"] = (
                await _seed_staff_messages(session, users, owner, conv_map)
            ).as_dict()
            req_map, req_counts = await _seed_account_requests(
                session, users, tickets_map
            )
            result.counts["account_requests"] = req_counts.as_dict()
            req_c, req_e = await _seed_account_request_children(session, users, req_map)
            result.counts["account_request_comments"] = req_c.as_dict()
            result.counts["account_request_events"] = req_e.as_dict()
            # Notifications come last: some reference conversations and account
            # requests, so those rows must exist first for the foreign keys.
            result.counts["notifications"] = (
                await _seed_notifications(session, users, tickets_map)
            ).as_dict()

            owner_after = await _owner_row(session)
            result.owner_after = owner_after
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

    return result


# --------------------------------------------------------------------------- #
# Verification / reporting
# --------------------------------------------------------------------------- #


def _label(value) -> str:
    """Human-readable label for an enum-or-string grouping key."""
    return str(getattr(value, "value", value))


async def read_counts(session_factory=None) -> dict:
    """Read back the current row counts and demo-namespace record counts."""
    factory = session_factory or async_session
    async with factory() as session:
        total_users = (await session.exec(select(func.count(User.id)))).one()
        by_role = (
            await session.exec(
                select(User.role, func.count(User.id)).group_by(User.role)
            )
        ).all()
        tickets_total = (await session.exec(select(func.count(Ticket.id)))).one()
        by_status = (
            await session.exec(
                select(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status)
            )
        ).all()
        by_priority = (
            await session.exec(
                select(Ticket.priority, func.count(Ticket.id)).group_by(Ticket.priority)
            )
        ).all()
        assigned = (
            await session.exec(
                select(func.count(Ticket.id)).where(
                    Ticket.assignee_user_id.is_not(None)
                )
            )
        ).one()
        demo_users_count = (
            await session.exec(
                select(func.count(User.id)).where(
                    User.username.like("demo\\_%", escape="\\")
                )
            )
        ).one()
        return {
            "users_total": int(total_users or 0),
            "users_by_role": {_label(r): int(c) for r, c in by_role},
            "demo_users": int(demo_users_count or 0),
            "tickets_total": int(tickets_total or 0),
            "tickets_by_status": {_label(s): int(c) for s, c in by_status},
            "tickets_by_priority": {_label(p): int(c) for p, c in by_priority},
            "tickets_assigned": int(assigned or 0),
            "tickets_unassigned": int(tickets_total or 0) - int(assigned or 0),
            "comments": int(
                (await session.exec(select(func.count(Comment.id)))).one() or 0
            ),
            "history": int(
                (await session.exec(select(func.count(TicketHistory.id)))).one() or 0
            ),
            "notifications": int(
                (await session.exec(select(func.count(Notification.id)))).one() or 0
            ),
            "attachments": int(
                (await session.exec(select(func.count(Attachment.id)))).one() or 0
            ),
            "staff_conversations": int(
                (await session.exec(select(func.count(StaffConversation.id)))).one()
                or 0
            ),
            "staff_messages": int(
                (await session.exec(select(func.count(StaffMessage.id)))).one() or 0
            ),
            "account_requests": int(
                (
                    await session.exec(select(func.count(AccountManagementRequest.id)))
                ).one()
                or 0
            ),
            "account_request_comments": int(
                (await session.exec(select(func.count(AccountRequestComment.id)))).one()
                or 0
            ),
            "account_request_events": int(
                (await session.exec(select(func.count(AccountRequestEvent.id)))).one()
                or 0
            ),
            "feedback": int(
                (await session.exec(select(func.count(TicketFeedback.id)))).one() or 0
            ),
            "internal_messages": int(
                (await session.exec(select(func.count(InternalMessage.id)))).one() or 0
            ),
            "internal_message_recipients": int(
                (
                    await session.exec(select(func.count(InternalMessageRecipient.id)))
                ).one()
                or 0
            ),
        }


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _print_result(result: SeedResult) -> None:
    print(f"\nDemo seed namespace: {MARKER}")
    print(f"Upload dir         : {result.upload_root}")
    print("\nPer-entity counts (inserted / reused / conflicts / failed):")
    for name, counts in result.counts.items():
        print(
            f"  {name:<28} {counts['inserted']:>6} / {counts['reused']:>6} / "
            f"{counts['skipped_conflicts']:>3} / {counts['failed']:>3}"
        )
    print("\nExpected dataset size:", json.dumps(result.expected))
    print("Owner unchanged during seed:", result.owner_before == result.owner_after)
    if result.conflicts:
        print("CONFLICTS:")
        for line in result.conflicts:
            print("  -", line)


def _print_counts(counts: dict) -> None:
    print("\n=== Live database counts (read back) ===")
    print(f"users total       : {counts['users_total']}")
    print(f"users by role     : {json.dumps(counts['users_by_role'])}")
    print(f"demo users        : {counts['demo_users']}")
    print(f"tickets total     : {counts['tickets_total']}")
    print(f"tickets by status : {json.dumps(counts['tickets_by_status'])}")
    print(f"tickets by priority: {json.dumps(counts['tickets_by_priority'])}")
    print(
        f"tickets assigned  : {counts['tickets_assigned']} (unassigned {counts['tickets_unassigned']})"
    )
    print(f"comments          : {counts['comments']}")
    print(f"history           : {counts['history']}")
    print(f"notifications     : {counts['notifications']}")
    print(f"attachments       : {counts['attachments']}")
    print(f"staff conversations: {counts['staff_conversations']}")
    print(f"staff messages    : {counts['staff_messages']}")
    print(f"account requests  : {counts['account_requests']}")
    print(f"acct req comments : {counts['account_request_comments']}")
    print(f"acct req events   : {counts['account_request_events']}")


async def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Seed the isolated demo dataset (INSERT-only, idempotent)."
    )
    parser.add_argument(
        "--size",
        type=int,
        choices=sorted(_ROLE_SPLITS),
        default=100,
        help="Number of application users to target (default: 100).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Compute and print the full insertion plan without opening a write "
            "transaction or touching the database."
        ),
    )
    parser.add_argument("--confirm", default=os.environ.get(CONFIRM_ENV))
    # `--verify` is the brief's name for `--verify-only`; both do the same thing
    # (report current rows, insert nothing).
    parser.add_argument(
        "--verify",
        "--verify-only",
        dest="verify_only",
        action="store_true",
        help="Report current row counts without inserting anything.",
    )
    # `--confirm-production` acknowledges the demo deployment's declared
    # production environment. It is an explicit, visible act, but it does NOT
    # replace the confirmation token and skips no other guard.
    parser.add_argument(
        "--confirm-production",
        dest="confirm_production",
        action="store_true",
        help=(
            "Acknowledge that the target declares ENVIRONMENT=production (the "
            "college-demo deployment). Still requires the confirmation token."
        ),
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        plan = use_plan(plan_for(args.size))
    except SeedRefused as exc:
        print(f"Seed refused: {exc}", file=sys.stderr)
        return 2

    # The dry-run deliberately skips the target/confirmation guards: it performs
    # no I/O, so an operator can inspect the plan before configuring anything.
    if args.dry_run:
        report = dry_run_report(plan)
        if args.json:
            print(json.dumps(report, indent=2))
        else:
            _print_dry_run(report)
        return 0

    try:
        assert_confirm(args.confirm)
        environ = dict(os.environ)
        if args.confirm_production:
            # Scoped to this check only; the confirm token above is still
            # mandatory and every other guard below still runs.
            environ[PRODUCTION_OVERRIDE_ENV] = PRODUCTION_OVERRIDE_VALUE
        assert_not_production(environ)
        assert_neon_target(settings.DATABASE_URL)
        upload_root = assert_safe_upload_dir(
            os.environ.get(UPLOAD_ENV, DEMO_UPLOAD_DIR)
        )
    except SeedRefused as exc:
        print(f"Seed refused: {exc}", file=sys.stderr)
        return 2

    print(
        f"Target: {redacted_target(settings.DATABASE_URL)} "
        f"(namespace {MARKER}, size {plan.size}, anchor {plan.anchor.isoformat()})"
    )

    if args.verify_only:
        counts = await read_counts()
        if args.json:
            print(json.dumps(counts, indent=2))
        else:
            _print_counts(counts)
        return 0

    try:
        result = await seed(upload_root)
    except SeedRefused as exc:
        print(f"Seed refused: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - operator-facing failure summary
        print(f"Seed failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps({"result": result.as_dict()}, indent=2))
    else:
        _print_result(result)
    counts = await read_counts()
    if args.json:
        print(json.dumps({"counts": counts}, indent=2))
    else:
        _print_counts(counts)
    return 0 if not result.conflicts else 3


def _print_dry_run(report: dict) -> None:
    expected = report["expected"]
    derived = report["derived"]
    print(f"\nDRY RUN — no database connection, no writes (namespace {MARKER})")
    print(f"Anchor (UTC)        : {report['anchor']}")
    print(f"Dataset size        : {expected['size']} users")
    print(
        f"Users               : {expected['users_total']} total "
        f"(1 owner, {expected['admins']} admins, {expected['agents']} agents, "
        f"{expected['customers']} customers)"
    )
    print(
        f"Inactive accounts   : {expected['inactive_customers']} customers, "
        f"{expected['inactive_agents']} agents"
    )
    print(f"Tickets             : {expected['tickets']}")
    print(f"  by status         : {json.dumps(expected['tickets_by_status'])}")
    print(f"  by priority       : {json.dumps(expected['tickets_by_priority'])}")
    print(
        f"  active            : {derived['active_tickets']} "
        f"(unassigned {derived['unassigned_active']}, "
        f"{derived['unassigned_active_pct']}% of active)"
    )
    print(f"  urgent active     : {derived['urgent_active']}")
    print(f"  created last 14d  : {derived['created_in_last_14_days']}")
    print(f"  aging > 7 days    : {derived['aging_over_7_days']}")
    print(f"  unassigned > 24h  : {derived['unassigned_over_24h']}")
    print(
        f"Comments            : {expected['comments']} "
        f"(internal notes {expected['internal_notes']})"
    )
    print(f"History events      : {expected['history']}")
    print(f"Notifications       : {expected['notifications']}")
    print(f"Attachments         : {expected['attachments']}")
    print(
        f"Staff conversations : {expected['staff_conversations']} "
        f"({expected['staff_messages']} messages)"
    )
    print(f"Account requests    : {expected['account_requests']}")
    print(f"Feedback            : {expected['feedback']}")
    print(f"Internal messages   : {expected['internal_messages']}")


def main() -> int:
    """Synchronous entry point for ``python -m app.commands.seed_demo_data``."""
    return asyncio.run(_main(sys.argv[1:]))


if __name__ == "__main__":
    raise SystemExit(main())
