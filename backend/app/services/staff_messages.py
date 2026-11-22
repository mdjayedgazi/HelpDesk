"""Business rules for universal staff-to-staff private messaging.

Any two eligible staff members (AGENT/ADMIN/OWNER) can hold a 1:1 conversation.
Nothing in this module is reachable by a customer: the router's dependency
already restricts every endpoint to staff roles, and each function re-checks
that the requesting user is a participant of the conversation being touched.

Authorization is derived from the conversation's two participant columns, which
are always written in canonical order (smaller UUID first) so a pair maps to
exactly one thread regardless of who started it.
"""

import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, status
from sqlalchemy import and_, case, func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.enums.enums import NotificationType, Role
from app.models.staff_message import (
    StaffConversation,
    StaffMessage,
    StaffMessageMention,
)
from app.models.user import User
from app.schemas.staff_messages import StaffConversationRead
from app.services.notifications import create_notification

# The preview stored in the inbox list is deliberately short.
PREVIEW_LENGTH = 140

# Roles allowed to use internal staff messaging. Customers are excluded
# everywhere; the router dependency enforces the same set.
STAFF_ROLES: tuple[Role, ...] = (Role.AGENT, Role.ADMIN, Role.OWNER)


def is_staff_role(role: Role) -> bool:
    return role in STAFF_ROLES


def canonical_pair(first: uuid.UUID, second: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Return the two participant ids in canonical (ascending) order."""
    return (first, second) if str(first) <= str(second) else (second, first)


def is_participant(conversation: StaffConversation, user: User) -> bool:
    return user.id in (conversation.participant_a_id, conversation.participant_b_id)


def counterpart_id(conversation: StaffConversation, viewer: User) -> uuid.UUID:
    if conversation.participant_a_id == viewer.id:
        return conversation.participant_b_id
    return conversation.participant_a_id


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


async def eligible_recipient(
    session: AsyncSession,
    *,
    sender: User,
    recipient_user_id: uuid.UUID,
) -> User:
    """Resolve and validate a conversation recipient.

    The recipient must exist, be active, hold a staff role, and not be the
    sender. Any failure is a ``404``/``422`` that never reveals whether the
    account exists to an unauthorized caller; here the caller is already an
    authenticated staff member, so a clear 4xx is appropriate.
    """
    if recipient_user_id == sender.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="You cannot start a conversation with yourself",
        )
    recipient = await session.get(User, recipient_user_id)
    if recipient is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found",
        )
    if not recipient.is_active or not is_staff_role(recipient.role):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This employee is not available for internal messaging",
        )
    return recipient


async def find_or_create_conversation(
    session: AsyncSession,
    *,
    sender: User,
    recipient: User,
    subject: str | None,
) -> StaffConversation:
    """Return the pair's existing conversation, or create it. Caller commits.

    The canonical pair makes this idempotent: whichever participant starts,
    the same unique row is used. A concurrent creator is handled at the router
    by re-reading after a unique violation.
    """
    a_id, b_id = canonical_pair(sender.id, recipient.id)
    conversation = (
        await session.exec(
            select(StaffConversation).where(
                StaffConversation.participant_a_id == a_id,
                StaffConversation.participant_b_id == b_id,
            )
        )
    ).first()
    if conversation is not None:
        return conversation

    conversation = StaffConversation(
        participant_a_id=a_id,
        participant_b_id=b_id,
        subject=subject
        or f"Conversation between {sender.full_name} and {recipient.full_name}",
    )
    session.add(conversation)
    return conversation


async def conversation_summary(
    session: AsyncSession,
    conversation: StaffConversation,
    viewer: User,
) -> StaffConversationRead:
    """Aggregates for one conversation (detail view)."""
    summaries = await conversation_summaries(session, [conversation], viewer)
    return summaries[0]


async def conversation_summaries(
    session: AsyncSession,
    conversations: list[StaffConversation],
    viewer: User,
) -> list[StaffConversationRead]:
    """Build inbox rows with a constant number of queries.

    Counts, latest messages and the participant profiles are fetched in bulk
    for the whole page, so the inbox never issues an N+1 query per thread.
    """
    if not conversations:
        return []

    ids = [conversation.id for conversation in conversations]
    user_ids = {
        user_id
        for conversation in conversations
        for user_id in (conversation.participant_a_id, conversation.participant_b_id)
    }

    aggregate_rows = (
        await session.exec(
            select(
                StaffMessage.conversation_id,
                func.count(StaffMessage.id),
                func.coalesce(
                    func.sum(
                        case(
                            (
                                and_(
                                    StaffMessage.sender_user_id != viewer.id,
                                    StaffMessage.read_at.is_(None),
                                ),
                                1,
                            ),
                            else_=0,
                        )
                    ),
                    0,
                ),
            )
            .where(StaffMessage.conversation_id.in_(ids))
            .group_by(StaffMessage.conversation_id)
        )
    ).all()
    aggregates = {
        conversation_id: (int(message_count), int(unread_count))
        for conversation_id, message_count, unread_count in aggregate_rows
    }

    def latest_rows(*, incoming_only: bool):
        row_number = func.row_number().over(
            partition_by=StaffMessage.conversation_id,
            order_by=(StaffMessage.created_at.desc(), StaffMessage.id.desc()),
        )
        statement = select(
            StaffMessage.conversation_id,
            StaffMessage.body,
            StaffMessage.sender_user_id,
            StaffMessage.created_at,
            row_number.label("row_number"),
        ).where(StaffMessage.conversation_id.in_(ids))
        if incoming_only:
            statement = statement.where(StaffMessage.sender_user_id != viewer.id)
        ranked = statement.subquery()
        return select(
            ranked.c.conversation_id,
            ranked.c.body,
            ranked.c.sender_user_id,
            ranked.c.created_at,
        ).where(ranked.c.row_number == 1)

    latest = {
        conversation_id: (body, sender_id, created_at)
        for conversation_id, body, sender_id, created_at in (
            await session.exec(latest_rows(incoming_only=False))
        ).all()
    }
    latest_incoming = {
        conversation_id: (body, created_at)
        for conversation_id, body, _sender_id, created_at in (
            await session.exec(latest_rows(incoming_only=True))
        ).all()
    }

    users = {
        user.id: user
        for user in (
            await session.exec(select(User).where(User.id.in_(user_ids)))
        ).all()
    }

    result: list[StaffConversationRead] = []
    for conversation in conversations:
        message_count, unread_count = aggregates.get(conversation.id, (0, 0))
        last_message = latest.get(conversation.id)
        last_received = latest_incoming.get(conversation.id)
        participant_a = users.get(conversation.participant_a_id)
        participant_b = users.get(conversation.participant_b_id)
        other = (
            participant_b
            if conversation.participant_a_id == viewer.id
            else participant_a
        )

        result.append(
            StaffConversationRead(
                id=conversation.id,
                subject=conversation.subject,
                participant_a_id=conversation.participant_a_id,
                participant_b_id=conversation.participant_b_id,
                counterpart_user_id=other.id if other is not None else None,
                counterpart_full_name=other.full_name
                if other is not None
                else "Employee",
                counterpart_role=other.role if other is not None else None,
                counterpart_image_url=other.image_url if other is not None else None,
                created_at=conversation.created_at,
                last_message_at=conversation.last_message_at,
                message_count=message_count,
                unread_count=unread_count,
                last_message_preview=(
                    last_message[0][:PREVIEW_LENGTH]
                    if last_message is not None
                    else None
                ),
                last_message_sender_user_id=(
                    last_message[1] if last_message is not None else None
                ),
                last_received_preview=(
                    last_received[0][:PREVIEW_LENGTH]
                    if last_received is not None
                    else None
                ),
                last_received_at=(
                    last_received[1] if last_received is not None else None
                ),
            )
        )
    return result


async def validate_mentions(
    session: AsyncSession,
    *,
    sender: User,
    mentioned_user_ids: list[uuid.UUID],
) -> list[uuid.UUID]:
    """Validate and de-duplicate mentioned employees for an internal message.

    Each id must reference an existing, active, staff-role account that is not
    the sender. Unknown ids, inactive accounts, customers and self-mentions are
    rejected. The result is de-duplicated while preserving first-seen order, so
    a repeated mention of the same person is stored (and notified) once.
    """
    if not mentioned_user_ids:
        return []

    unique_ids: list[uuid.UUID] = []
    seen: set[uuid.UUID] = set()
    for user_id in mentioned_user_ids:
        if user_id in seen:
            continue
        seen.add(user_id)
        unique_ids.append(user_id)

    rows = (await session.exec(select(User).where(User.id.in_(unique_ids)))).all()
    by_id = {user.id: user for user in rows}

    for user_id in unique_ids:
        user = by_id.get(user_id)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="A mentioned employee does not exist",
            )
        if user.id == sender.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="You cannot mention yourself",
            )
        if not user.is_active or not is_staff_role(user.role):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Only active staff members can be mentioned",
            )
    return unique_ids


def stage_staff_mentions(
    session: AsyncSession,
    *,
    message: StaffMessage,
    mentioned_user_ids: list[uuid.UUID],
) -> list[StaffMessageMention]:
    """Stage mention rows for a staff message. Caller commits."""
    mentions: list[StaffMessageMention] = []
    for user_id in mentioned_user_ids:
        mention = StaffMessageMention(
            message_id=message.id,
            mentioned_user_id=user_id,
        )
        session.add(mention)
        mentions.append(mention)
    return mentions


def send_message(
    session: AsyncSession,
    *,
    conversation: StaffConversation,
    sender: User,
    body: str,
    mentioned_user_ids: list[uuid.UUID] | None = None,
) -> StaffMessage:
    """Stage a private message, its mentions and the recipient's notification.

    The message body is never copied into the notification: notifications can be
    listed by a notification endpoint, so they stay free of conversation
    content.

    Each conversation participant other than the sender is notified exactly
    once. A recipient who is also mentioned gets a single mention-typed
    notification instead of a duplicate "new message" one.
    """
    message = StaffMessage(
        conversation_id=conversation.id,
        sender_user_id=sender.id,
        body=body,
    )
    session.add(message)

    conversation.last_message_at = datetime.now(UTC)
    session.add(conversation)

    mentioned: list[uuid.UUID] = list(mentioned_user_ids or [])
    if mentioned:
        stage_staff_mentions(session, message=message, mentioned_user_ids=mentioned)

    recipient_id = counterpart_id(conversation, sender)
    mentioned_set = set(mentioned)

    # The conversation counterpart receives exactly ONE notification for the
    # message. If they were also mentioned it is typed as a mention, so the
    # notification reflects the mention without ever duplicating the alert.
    #
    # A mentioned employee who is *not* a participant is deliberately NOT
    # notified: a 1:1 thread is participant-scoped, so they could not open it,
    # and a notification deep-link would 404 (and would leak the thread's
    # existence). The structured mention row is still stored for rendering.
    if recipient_id != sender.id:
        if recipient_id in mentioned_set:
            create_notification(
                session,
                recipient_user_id=recipient_id,
                related_conversation_id=conversation.id,
                type=NotificationType.STAFF_MENTION,
                title=f"{sender.full_name} mentioned you",
                message="You were mentioned in a private staff message.",
            )
        else:
            create_notification(
                session,
                recipient_user_id=recipient_id,
                related_conversation_id=conversation.id,
                type=NotificationType.STAFF_MESSAGE_RECEIVED,
                title=f"New private message from {sender.full_name}",
                message="A staff member sent you a private message.",
            )

    return message


async def message_mentions(
    session: AsyncSession, message_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[uuid.UUID]]:
    """Map each message id to the employees it mentions (bulk, for a page)."""
    if not message_ids:
        return {}
    rows = (
        await session.exec(
            select(
                StaffMessageMention.message_id,
                StaffMessageMention.mentioned_user_id,
            ).where(StaffMessageMention.message_id.in_(message_ids))
        )
    ).all()
    result: dict[uuid.UUID, list[uuid.UUID]] = {}
    for message_id, user_id in rows:
        result.setdefault(message_id, []).append(user_id)
    return result


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
    now = datetime.now(UTC)
    for row in rows:
        row.read_at = now
        session.add(row)
    return len(rows)
