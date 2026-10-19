"""Notification helpers."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.enums import NotificationType
from app.models.notification import Notification


def create_notification(
    session: AsyncSession,
    *,
    recipient_user_id: uuid.UUID,
    title: str,
    message: str,
    type: NotificationType,
    related_ticket_id: uuid.UUID | None = None,
    related_conversation_id: uuid.UUID | None = None,
) -> Notification:
    """Stage a notification row. The caller commits.

    Notifications are only ever created for a specific local user id, so a
    client can never choose the recipient of a notification directly.
    """
    notification = Notification(
        recipient_user_id=recipient_user_id,
        related_ticket_id=related_ticket_id,
        related_conversation_id=related_conversation_id,
        type=type,
        title=title[:180],
        message=message[:500],
    )
    session.add(notification)
    return notification
