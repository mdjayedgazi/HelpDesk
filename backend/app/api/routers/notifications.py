import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import func, select

from app.core.auth import user_dependency
from app.core.database import session_Dependency
from app.core.rate_limit import rate_limit
from app.enums.enums import NotificationType
from app.models.internal_message import InternalMessageRecipient
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notifications import (
    NotificationRead,
    NotificationUnreadCount,
    NotificationUpdate,
)

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])

# The notification types grouped into the panel's category filters. Keeping the
# grouping here (server-side) means the client never has to know which type
# belongs to which bucket, and an unknown category is a clean 422.
TICKET_TYPES: tuple[NotificationType, ...] = (
    NotificationType.TICKET_ASSIGNED,
    NotificationType.NEW_COMMENT,
    NotificationType.STATUS_CHANGED,
    NotificationType.PRIORITY_CHANGED,
    NotificationType.TICKET_NEEDS_ASSIGNMENT,
    NotificationType.TICKET_CREATED,
    NotificationType.TICKET_RESOLVED,
)
MESSAGE_TYPES: tuple[NotificationType, ...] = (
    NotificationType.STAFF_MESSAGE_RECEIVED,
    NotificationType.OWNER_MESSAGE_RECEIVED,
    NotificationType.INTERNAL_MESSAGE_RECEIVED,
)
ACCOUNT_TYPES: tuple[NotificationType, ...] = (
    NotificationType.ESCALATION_CREATED,
    NotificationType.ESCALATION_UPDATED,
)

CATEGORY_TYPES: dict[str, tuple[NotificationType, ...]] = {
    "tickets": TICKET_TYPES,
    "messages": MESSAGE_TYPES,
    "account_requests": ACCOUNT_TYPES,
}


@router.get("/unread-count", response_model=NotificationUnreadCount)
async def unread_count(
    session: session_Dependency,
    user: user_dependency,
    _rate_limit: Annotated[None, Depends(rate_limit("notification_poll"))],
) -> NotificationUnreadCount:
    """The current user's unread totals (the bell badge's source of truth).

    Counted in SQL so the badge is exact even when the client has only loaded a
    page of the list.
    """
    rows = (
        await session.exec(
            select(Notification.type, func.count())
            .where(
                Notification.recipient_user_id == user.id,
                Notification.is_read.is_(False),
            )
            .group_by(Notification.type)
        )
    ).all()

    buckets = {"tickets": 0, "messages": 0, "account_requests": 0}
    total = 0
    for ntype, count in rows:
        total += count
        for category, types in CATEGORY_TYPES.items():
            if ntype in types:
                buckets[category] += count
                break

    return NotificationUnreadCount(count=total, **buckets)


@router.get("", response_model=list[NotificationRead])
async def list_my_notifications(
    session: session_Dependency,
    user: user_dependency,
    _rate_limit: Annotated[None, Depends(rate_limit("notification_poll"))],
    is_read: Annotated[bool | None, Query()] = None,
    category: Annotated[
        str | None, Query(pattern="^(tickets|messages|account_requests)$")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Notification]:
    """List only the authenticated user's notifications."""
    statement = select(Notification).where(Notification.recipient_user_id == user.id)
    if is_read is not None:
        statement = statement.where(Notification.is_read == is_read)
    if category is not None:
        statement = statement.where(Notification.type.in_(CATEGORY_TYPES[category]))

    statement = (
        statement.order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.exec(statement)
    return list(result.all())


@router.patch("/{notification_id}", response_model=NotificationRead)
async def update_notification(
    notification_id: uuid.UUID,
    payload: NotificationUpdate,
    session: session_Dependency,
    user: user_dependency,
) -> Notification:
    notification = await _load_own_notification(session, notification_id, user)

    notification.is_read = payload.is_read
    session.add(notification)
    # Marking an internal-message notification read also marks the underlying
    # message read, so the two unread indicators never disagree.
    if payload.is_read:
        await _sync_internal_message_reads(session, user.id, [notification])
    await session.commit()
    await session.refresh(notification)
    return notification


@router.post("/read-all", response_model=dict[str, int])
async def mark_all_notifications_read(
    session: session_Dependency,
    user: user_dependency,
) -> dict[str, int]:
    """Mark every unread notification of the current user as read."""
    statement = select(Notification).where(
        Notification.recipient_user_id == user.id,
        Notification.is_read.is_(False),
    )
    result = await session.exec(statement)
    notifications = list(result.all())
    for notification in notifications:
        notification.is_read = True
        session.add(notification)

    await _sync_internal_message_reads(session, user.id, notifications)
    await session.commit()
    return {"updated": len(notifications)}


async def _load_own_notification(
    session, notification_id: uuid.UUID, user: User
) -> Notification:
    """Fetch a notification only if it belongs to ``user``.

    Somebody else's notification is a ``404`` (never ``403``) so the API does
    not reveal that it exists.
    """
    notification = await session.get(Notification, notification_id)
    if notification is None or notification.recipient_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )
    return notification


async def _sync_internal_message_reads(session, user_id, notifications) -> None:
    """Mark the reader's recipient rows read for the given notifications.

    Only rows the user actually owns can ever be touched, and only rows that are
    still unread, so the message's own unread state stays truthful.
    """
    message_ids = {
        n.related_internal_message_id
        for n in notifications
        if n.related_internal_message_id is not None
    }
    if not message_ids:
        return
    rows = (
        await session.exec(
            select(InternalMessageRecipient).where(
                InternalMessageRecipient.recipient_user_id == user_id,
                InternalMessageRecipient.message_id.in_(message_ids),
                InternalMessageRecipient.read_at.is_(None),
            )
        )
    ).all()
    now = datetime.now(UTC)
    for row in rows:
        row.read_at = now
        session.add(row)
