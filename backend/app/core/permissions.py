"""Central role-capability rules.

The local database is the single source of application authorization: the
authenticated user's role is read from PostgreSQL on every request (see
``app.core.auth.get_current_user``) and never taken from the request body.

Hierarchy
---------
``OWNER``
    The permanent, unique top-level role. It has every ``ADMIN`` capability
    (dashboard, ticket management, assignment) *plus* exclusive user-management
    authority: listing the directory, changing ordinary users' roles and
    activating/deactivating accounts. The Owner cannot be demoted or
    deactivated, and no normal request can create a second Owner.

``ADMIN``
    Administrative capabilities for HelpDesk itself (ticket management and the
    dashboard). Admins may view the user directory but may **not** change roles
    or account status: user management is Owner-only.

``AGENT``
    Authorized support workflows (assigned tickets, comments, status changes).
    Agents never gain administrative or user-management rights. The agent queue
    stays agent-only; holding ADMIN/OWNER does not grant agent-only actions.

``CUSTOMER``
    Customer ticket workflows only.
"""

from app.enums.enums import Role

# Roles that carry administrative (help-desk management) capabilities.
ADMIN_ROLES: frozenset[Role] = frozenset({Role.ADMIN, Role.OWNER})

# Roles that work on tickets (agents and both administrative roles).
STAFF_ROLES: frozenset[Role] = frozenset({Role.AGENT, Role.ADMIN, Role.OWNER})


def is_owner_role(role: Role) -> bool:
    """Whether ``role`` is the permanent Owner role."""
    return role == Role.OWNER


def is_admin_role(role: Role) -> bool:
    """Whether ``role`` has administrative capabilities (ADMIN or OWNER)."""
    return role in ADMIN_ROLES


def is_staff_role(role: Role) -> bool:
    """Whether ``role`` may act on tickets (AGENT, ADMIN or OWNER)."""
    return role in STAFF_ROLES


def can_manage_users(role: Role) -> bool:
    """Whether ``role`` may change roles and account status. Owner only."""
    return role == Role.OWNER


# Roles that may open a private conversation with the Owner and open
# account-management requests. The Owner does not need either workflow; a
# customer must never reach them.
STAFF_MESSAGING_ROLES: frozenset[Role] = frozenset({Role.AGENT, Role.ADMIN})


def can_message_owner(role: Role) -> bool:
    """Whether ``role`` may start/use a private conversation with the Owner."""
    return role in STAFF_MESSAGING_ROLES


def can_create_account_request(role: Role) -> bool:
    """Whether ``role`` may open an account-management (escalation) request."""
    return role in STAFF_MESSAGING_ROLES


def can_review_account_request(role: Role) -> bool:
    """Whether ``role`` may decide (approve/reject/complete) a request.

    Reviewers are ADMIN/OWNER accounts; the request creator can never decide
    their own request (enforced by the router).
    """
    return is_admin_role(role)
