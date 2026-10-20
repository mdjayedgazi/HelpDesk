from enum import Enum


class Role(str, Enum):
    CUSTOMER = "customer"
    ADMIN = "admin"
    AGENT = "agent"
    # Permanent, unique top-level role. Exactly one OWNER may exist; it
    # controls role assignment and cannot be demoted or deactivated through the
    # regular user-management endpoints. See app/core/permissions.py.
    OWNER = "owner"


class AssignableRole(str, Enum):
    """Roles the Owner may assign through the user-management API.

    Deliberately excludes ``OWNER``: ownership is established only by the
    one-time ``app.commands.bootstrap_owner`` command, never through a normal
    role-change request.
    """

    CUSTOMER = "customer"
    AGENT = "agent"
    ADMIN = "admin"


class TicketStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_ON_CUSTOMER = "WAITING_ON_CUSTOMER"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class TicketPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class TicketCategory(str, Enum):
    """Customer-facing issue categories for a support request.

    The customer chooses a category; it is stored on the ticket so staff can
    triage and report without asking for the same information twice. ``OTHER``
    is the migration-safe default for tickets created before categories
    existed.
    """

    BILLING = "BILLING"
    ACCOUNT_ACCESS = "ACCOUNT_ACCESS"
    TECHNICAL = "TECHNICAL"
    OUTAGE = "OUTAGE"
    BUG = "BUG"
    ACCOUNT_MANAGEMENT = "ACCOUNT_MANAGEMENT"
    OTHER = "OTHER"


class ImpactLevel(str, Enum):
    """Customer-stated impact of an issue.

    This is *input* used by the ticket-priority policy
    (``app.services.tickets.PRIORITY_BY_IMPACT``); it is not the ticket
    priority itself. Customers describe real-world impact, the support policy
    maps it to a priority.
    """

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EscalationStatus(str, Enum):
    """Lifecycle of an account-management (admin escalation) request."""

    PENDING = "PENDING"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"


class EscalationCategory(str, Enum):
    """What kind of privileged account action is being requested."""

    ACCOUNT_RECOVERY = "ACCOUNT_RECOVERY"
    IDENTITY_LINKING = "IDENTITY_LINKING"
    PROFILE_CORRECTION = "PROFILE_CORRECTION"
    ROLE_OR_STATUS_CHANGE = "ROLE_OR_STATUS_CHANGE"
    OTHER = "OTHER"


class InternalAudience(str, Enum):
    """Who an Owner-composed internal message is addressed to.

    Mirrors the four options of the Owner Inbox compose form. ``INDIVIDUAL``
    always carries exactly one recipient (validated by the service); the other
    three resolve to the whole eligible group at send time and every resolved
    recipient is stored individually, so the intended audience stays auditable
    even after an employee's role changes.
    """

    EVERYONE = "everyone"
    AGENTS = "agents"
    ADMINS = "admins"
    INDIVIDUAL = "individual"


class NotificationType(str, Enum):
    TICKET_ASSIGNED = "TICKET_ASSIGNED"
    NEW_COMMENT = "NEW_COMMENT"
    STATUS_CHANGED = "STATUS_CHANGED"
    PRIORITY_CHANGED = "PRIORITY_CHANGED"
    # No eligible agent could be auto-assigned; the administrative queue is
    # notified so the ticket is never silently lost.
    TICKET_NEEDS_ASSIGNMENT = "TICKET_NEEDS_ASSIGNMENT"
    # Private staff -> Owner conversation activity.
    STAFF_MESSAGE_RECEIVED = "STAFF_MESSAGE_RECEIVED"
    # Private Owner -> staff conversation activity.
    OWNER_MESSAGE_RECEIVED = "OWNER_MESSAGE_RECEIVED"
    # Account-management (admin escalation) request activity.
    ESCALATION_CREATED = "ESCALATION_CREATED"
    ESCALATION_UPDATED = "ESCALATION_UPDATED"
    # The customer's ticket was received. A receipt only, never a workflow
    # signal, so the customer always knows their request landed.
    TICKET_CREATED = "TICKET_CREATED"
    # A ticket the customer owns became RESOLVED. Carries the "share feedback"
    # call to action; only created on the transition into RESOLVED (and only
    # while no feedback has been submitted), so resolving again never spams.
    TICKET_RESOLVED = "TICKET_RESOLVED"
    # A direct/broadcast message the Owner composed in the Owner Inbox and
    # addressed to an employee (never a customer, never the Owner).
    INTERNAL_MESSAGE_RECEIVED = "INTERNAL_MESSAGE_RECEIVED"
