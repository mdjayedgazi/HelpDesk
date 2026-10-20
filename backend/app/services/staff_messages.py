"""Business rules for the private staff <-> Owner messaging channel.

Only AGENT/ADMIN users and the single OWNER participate. Nothing in this
module is reachable by a customer: the router's dependency already restricts
every endpoint to staff roles, and each function re-checks that the requesting
user is a participant of the conversation being touched.
"""

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.enums.enums import NotificationType, Role
from app.models.staff_message import StaffConversation, StaffMessage
from app.models.user import User
from app.schemas.staff_messages import StaffConversationRead
from app.services.notifications import create_notification

# The preview stored in the inbox list is deliberately short.
PREVIEW_LENGTH = 140


async def get_owner(session: AsyncSession) -> User:
    """The single active Owner, or a clear error when none is configured."""
    owner = (await session.exec(select(User).where(User.role == Role.OWNER))).first()
    if owner is None or not owner.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The Owner account is not available",
        )
    return owner


def is_participant(conversation: StaffConversation, user: User) -> bool:
    return user.id in (conversation.staff_user_id, conversation.owner_user_id)


async def load_conversation(
    session: AsyncSession,
    conversation_id: uuid.UUID,
    user: User,
) -> StaffConversation:
    """Fetch a conversation the user participates in, or raise 404.

    Non-participants get ``404`` rather than ``403`` so the API never reveals
    that another staff member's private thread exists.
    """
    conversation = await session.get(StaffConversation, conversation_id)
    if conversation is None or not is_participant(conversation, user):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    return conversation


async def conversation_summary(
    session: AsyncSession,
    conversation: StaffConversation,
    viewer: User,
) -> StaffConversationRead:
    """Aggregates for the inbox: counts, unread, and a body-free preview."""
    message_count = (
        await session.exec(
            select(func.count())
            .select_from(StaffMessage)
            .where(StaffMessage.conversation_id == conversation.id)
        )
    ).one()

    unread_count = (
        await session.exec(
            select(func.count())
            .select_from(StaffMessage)
            .where(
                StaffMessage.conversation_id == conversation.id,
                StaffMessage.sender_user_id != viewer.id,
                StaffMessage.read_at.is_(None),
            )
        )
    ).one()

    last_message = (
        await session.exec(
            select(StaffMessage)
            .where(StaffMessage.conversation_id == conversation.id)
            .order_by(StaffMessage.created_at.desc(), StaffMessage.id.desc())
            .limit(1)
        )
    ).first()

    # The viewer's most recent *incoming* message. The Owner inbox is a list of
    # messages received from agents/admins, so its preview must never be the
    # Owner's own last reply.
    last_received = (
        await session.exec(
            select(StaffMessage)
            .where(
                StaffMessage.conversation_id == conversation.id,
                StaffMessage.sender_user_id != viewer.id,
            )
            .order_by(StaffMessage.created_at.desc(), StaffMessage.id.desc())
            .limit(1)
        )
    ).first()

    staff = await session.get(User, conversation.staff_user_id)
    owner = await session.get(User, conversation.owner_user_id)

    return StaffConversationRead(
        id=conversation.id,
        subject=conversation.subject,
        staff_user_id=conversation.staff_user_id,
        staff_full_name=staff.full_name if staff is not None else "Staff member",
        staff_role=staff.role if staff is not None else None,
        staff_image_url=staff.image_url if staff is not None else None,
        owner_user_id=conversation.owner_user_id,
        owner_image_url=owner.image_url if owner is not None else None,
        created_at=conversation.created_at,
        last_message_at=conversation.last_message_at,
        message_count=message_count,
        unread_count=unread_count,
        last_message_preview=(
            last_message.body[:PREVIEW_LENGTH] if last_message is not None else None
        ),
        last_message_sender_user_id=(
            last_message.sender_user_id if last_message is not None else None
        ),
        last_received_preview=(
            last_received.body[:PREVIEW_LENGTH] if last_received is not None else None
        ),
        last_received_at=(
            last_received.created_at if last_received is not None else None
        ),
    )


def send_message(
    session: AsyncSession,
    *,
    conversation: StaffConversation,
    sender: User,
    body: str,
) -> StaffMessage:
    """Stage a private message and the recipient's notification. Caller commits.

    The message body is never copied into the notification: notifications can
    be listed by a notification endpoint, so they stay free of conversation
    content.
    """
    message = StaffMessage(
        conversation_id=conversation.id,
        sender_user_id=sender.id,
        body=body,
    )
    session.add(message)

    conversation.last_message_at = datetime.now(timezone.utc)
    session.add(conversation)

    if sender.id == conversation.owner_user_id:
        recipient_id = conversation.staff_user_id
        notification_type = NotificationType.OWNER_MESSAGE_RECEIVED
        title = "The Owner replied to you"
        message_text = "The Owner sent you a private message."
    else:
        recipient_id = conversation.owner_user_id
        notification_type = NotificationType.STAFF_MESSAGE_RECEIVED
        title = f"New private message from {sender.full_name}"
        message_text = "A staff member sent you a private message."

    # Never notify the sender about their own message, and never notify a
    # different staff member: recipient_id always comes from the conversation.
    if recipient_id != sender.id:
        create_notification(
            session,
            recipient_user_id=recipient_id,
            related_conversation_id=conversation.id,
            type=notification_type,
            title=title,
            message=message_text,
        )

    return message


async def mark_conversation_read(
    session: AsyncSession,
    *,
    conversation: StaffConversation,
    reader: User,
) -> int:
    """Mark every message addressed to ``reader`` as read. Caller commits."""
    statement = select(StaffMessage).where(
        StaffMessage.conversation_id == conversation.id,
        StaffMessage.sender_user_id != reader.id,
        StaffMessage.read_at.is_(None),
    )
    rows = (await session.exec(statement)).all()
    now = datetime.now(timezone.utc)
    for row in rows:
        row.read_at = now
        session.add(row)
    return len(rows)
