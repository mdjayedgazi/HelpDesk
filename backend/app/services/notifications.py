"""Notification helpers.

Every notification row is created from one of these helpers so the recipient
rules stay in one place and cannot drift between the routers. The recipient is
always a concrete local user id resolved server-side from the database (the
authenticated user, the ticket owner/assignee, the message recipient rows), so
a request body can never choose who gets notified.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.enums.enums import NotificationType, Role
from app.models.notification import Notification
from app.models.user import User


def create_notification(
    session: AsyncSession,
    *,
    recipient_user_id: uuid.UUID,
    title: str,
    message: str,
    type: NotificationType,
    related_ticket_id: uuid.UUID | None = None,
    related_conversation_id: uuid.UUID | None = None,
    related_internal_message_id: uuid.UUID | None = None,
    related_account_request_id: uuid.UUID | None = None,
) -> Notification:
    """Stage a notification row. The caller commits.

    Notifications are only ever created for a specific local user id, so a
    client can never choose the recipient of a notification directly. The
    titles/messages are truncated to the column limits here so a long ticket
    title can never fail the write.
    """
    notification = Notification(
        recipient_user_id=recipient_user_id,
        related_ticket_id=related_ticket_id,
        related_conversation_id=related_conversation_id,
        related_internal_message_id=related_internal_message_id,
        related_account_request_id=related_account_request_id,
        type=type,
        title=title[:180],
        message=message[:500],
    )
    session.add(notification)
    return notification


async def active_admin_ids(
    session: AsyncSession, *, exclude_user_id: uuid.UUID | None = None
) -> set[uuid.UUID]:
    """Active ADMIN/OWNER accounts, optionally excluding one user.

    Used when a ticket has no assignee yet: the administrative queue is the
    real operational owner of "needs attention" work, so that is who is told.
    """
    statement = select(User.id).where(
        User.role.in_((Role.ADMIN, Role.OWNER)),
        User.is_active.is_(True),
    )
    if exclude_user_id is not None:
        statement = statement.where(User.id != exclude_user_id)
    return set((await session.exec(statement)).all())


def notify_many(
    session: AsyncSession,
    *,
    recipient_ids: set[uuid.UUID],
    title: str,
    message: str,
    type: NotificationType,
    actor_user_id: uuid.UUID | None = None,
    related_ticket_id: uuid.UUID | None = None,
    related_conversation_id: uuid.UUID | None = None,
    related_internal_message_id: uuid.UUID | None = None,
) -> int:
    """Stage one notification per recipient, never for the actor.

    Returns how many rows were staged. A set is used so a recipient that is
    both "assignee" and "admin" is only notified once.
    """
    recipients = {rid for rid in recipient_ids if rid is not None}
    if actor_user_id is not None:
        recipients.discard(actor_user_id)
    for recipient_id in recipients:
        create_notification(
            session,
            recipient_user_id=recipient_id,
            type=type,
            title=title,
            message=message,
            related_ticket_id=related_ticket_id,
            related_conversation_id=related_conversation_id,
            related_internal_message_id=related_internal_message_id,
        )
    return len(recipients)
