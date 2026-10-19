import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import select

from app.core.auth import user_dependency
from app.core.database import session_Dependency
from app.models.notification import Notification
from app.schemas.notifications import NotificationRead, NotificationUpdate

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationRead])
async def list_my_notifications(
    session: session_Dependency,
    user: user_dependency,
    is_read: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Notification]:
    """List only the authenticated user's notifications."""
    statement = select(Notification).where(
        Notification.recipient_user_id == user.id
    )
    if is_read is not None:
        statement = statement.where(Notification.is_read == is_read)

    statement = (
        statement.order_by(Notification.created_at.desc())
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
    notification = await session.get(Notification, notification_id)

    # Treat someone else's notification as "not found" so we do not reveal it.
    if notification is None or notification.recipient_user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Notification not found",
        )

    notification.is_read = payload.is_read
    session.add(notification)
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
    updated = 0
    for notification in result.all():
        notification.is_read = True
        session.add(notification)
        updated += 1

    await session.commit()
    return {"updated": updated}
