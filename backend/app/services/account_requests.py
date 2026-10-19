"""Business rules for account-management (admin escalation) requests.

The lifecycle is a small state machine. Every transition is written to the
append-only ``account_management_request_events`` trail, and the request row
keeps the decision audit (who decided, when, why). Nothing here can change a
user's identity: the endpoints only move the request through its states.
"""

import uuid

from fastapi import HTTPException, status
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.permissions import is_admin_role
from app.enums.enums import (
    EscalationStatus,
    NotificationType,
    Role,
)
from app.models.account_request import (
    AccountManagementRequest,
    AccountRequestEvent,
)
from app.models.user import User
from app.services.notifications import create_notification

ALLOWED_ESCALATION_TRANSITIONS: dict[EscalationStatus, set[EscalationStatus]] = {
    EscalationStatus.PENDING: {
        EscalationStatus.IN_REVIEW,
        EscalationStatus.APPROVED,
        EscalationStatus.REJECTED,
    },
    EscalationStatus.IN_REVIEW: {
        EscalationStatus.APPROVED,
        EscalationStatus.REJECTED,
    },
    EscalationStatus.APPROVED: {EscalationStatus.COMPLETED},
    EscalationStatus.REJECTED: set(),
    EscalationStatus.COMPLETED: set(),
}

# Comments remain possible while the request is still actionable. A decided
# (rejected/completed) request is closed to further discussion and its record
# stays immutable.
COMMENTABLE_ESCALATION_STATUSES: frozenset[EscalationStatus] = frozenset(
    {
        EscalationStatus.PENDING,
        EscalationStatus.IN_REVIEW,
        EscalationStatus.APPROVED,
    }
)


def validate_escalation_transition(
    current: EscalationStatus, new: EscalationStatus
) -> None:
    if new == current:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"This request is already {current.value}",
        )
    if new not in ALLOWED_ESCALATION_TRANSITIONS[current]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot change status from {current.value} to {new.value}",
        )


def can_view_request(user: User, request: AccountManagementRequest) -> bool:
    """The creator and authorized administrators may read a request."""
    if is_admin_role(user.role):
        return True
    return request.created_by_user_id == user.id


async def load_visible_request(
    session: AsyncSession,
    request_id: uuid.UUID,
    user: User,
) -> AccountManagementRequest:
    """Fetch a request the user may see, or raise 404.

    ``404`` (not ``403``) keeps the existence of other users' requests hidden
    from agents.
    """
    request = await session.get(AccountManagementRequest, request_id)
    if request is None or not can_view_request(user, request):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Account request not found",
        )
    return request


def record_request_event(
    session: AsyncSession,
    *,
    request: AccountManagementRequest,
    actor: User,
    event_type: str,
    old_value: dict | None,
    new_value: dict | None,
) -> AccountRequestEvent:
    """Stage an audit event. The caller commits."""
    event = AccountRequestEvent(
        request_id=request.id,
        actor_user_id=actor.id,
        event_type=event_type,
        old_value=old_value,
        new_value=new_value,
    )
    session.add(event)
    return event


async def _active_reviewers(
    session: AsyncSession, *, exclude_user_id: uuid.UUID | None
) -> list[User]:
    statement = select(User).where(
        User.role.in_((Role.ADMIN, Role.OWNER)),
        User.is_active.is_(True),
    )
    if exclude_user_id is not None:
        statement = statement.where(User.id != exclude_user_id)
    return list((await session.exec(statement)).all())


async def notify_reviewers(
    session: AsyncSession,
    *,
    request: AccountManagementRequest,
    actor: User,
) -> None:
    """Tell active ADMIN/OWNER users (except the actor) about new activity."""
    for reviewer in await _active_reviewers(session, exclude_user_id=actor.id):
        create_notification(
            session,
            recipient_user_id=reviewer.id,
            related_ticket_id=request.ticket_id,
            type=NotificationType.ESCALATION_CREATED,
            title="New account request",
            message=(
                "An account-management request needs review. "
                f"Request id {request.id}."
            ),
        )


def notify_creator(
    session: AsyncSession,
    *,
    request: AccountManagementRequest,
    actor: User,
    title: str,
    message: str,
) -> None:
    """Notify the requester about a decision/comment, never the actor."""
    if request.created_by_user_id == actor.id:
        return
    create_notification(
        session,
        recipient_user_id=request.created_by_user_id,
        related_ticket_id=request.ticket_id,
        type=NotificationType.ESCALATION_UPDATED,
        title=title,
        message=message,
    )
