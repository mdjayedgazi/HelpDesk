"""Universal private messaging between staff members (AGENT/ADMIN/OWNER).

Authorization summary (enforced here, in the backend, not just in the UI):

* every endpoint requires a staff role via ``staff_dependency`` - a CUSTOMER
  receives ``403`` from the dependency and can never read, start, search, or
  send in a private conversation;
* any two eligible staff members can start a conversation with each other (the
  Owner is no longer a required participant);
* reading, replying and marking read all require being a participant of that
  specific conversation; anybody else gets ``404`` (an employee cannot even
  discover that another employee's thread exists);
* the recipient of a new conversation is validated server-side (must exist, be
  active, and hold a staff role);
* structured @mentions are validated against real, active staff accounts.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import String, case, cast, exists, func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.core.auth import staff_dependency
from app.core.database import session_Dependency
from app.core.rate_limit import rate_limit
from app.enums.enums import Role
from app.models.staff_message import StaffConversation, StaffMessage
from app.models.user import User
from app.schemas.staff_messages import (
    MarkReadResult,
    StaffConversationCreate,
    StaffConversationDetail,
    StaffConversationRead,
    StaffMessageCreate,
    StaffMessageRead,
)
from app.schemas.users import UserRead
from app.services.staff_messages import (
    STAFF_ROLES,
    conversation_summaries,
    conversation_summary,
    eligible_recipient,
    find_or_create_conversation,
    load_conversation,
    mark_conversation_read,
    message_mentions,
    send_message,
    validate_mentions,
)

router = APIRouter(prefix="/api/v1/staff-messages", tags=["staff-messages"])


async def _messages_with_mentions(
    session, messages: list[StaffMessage]
) -> list[StaffMessageRead]:
    """Serialize messages, attaching their structured mention ids in bulk."""
    mentions = await message_mentions(session, [message.id for message in messages])
    result: list[StaffMessageRead] = []
    for message in messages:
        read = StaffMessageRead.model_validate(message)
        read.mentioned_user_ids = mentions.get(message.id, [])
        result.append(read)
    return result


@router.get("/directory", response_model=list[UserRead])
async def search_staff_directory(
    session: session_Dependency,
    staff: staff_dependency,
    q: Annotated[str | None, Query(max_length=120)] = None,
    role: Annotated[Role | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[User]:
    """Search the eligible internal employee directory (any staff member).

    Returns only active AGENT/ADMIN/OWNER accounts other than the caller.
    Search is case-insensitive across display name, username and the account
    id, and supports an ``@``-prefix query from the mention composer (the
    leading ``@`` is stripped). Results are ordered so an exact username match
    comes first, then names that start with the query, then other partial
    matches.

    Customers never reach this endpoint (``403`` from the dependency), so the
    staff directory is never exposed to a customer.
    """
    if role is not None and role not in STAFF_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Only staff roles are searchable",
        )
    roles = (role,) if role is not None else STAFF_ROLES

    statement = select(User).where(
        User.role.in_(roles),
        User.is_active.is_(True),
        User.id != staff.id,
    )

    term = (q or "").strip().lstrip("@").strip()
    ordered = statement
    if term:
        like = f"%{term.lower()}%"
        statement = statement.where(
            or_(
                User.username.ilike(like),
                User.full_name.ilike(like),
                cast(User.id, String).ilike(like),
            )
        )
        # Rank: exact username first, then usernames/names that start with the
        # query, then other partial matches. Case-insensitive on both sides so
        # @Alice and @alice rank identically. ``case`` yields a small integer
        # sort key that works on both PostgreSQL and SQLite.
        prefix = f"{term.lower()}%"
        rank = case(
            (func.lower(User.username) == term.lower(), 0),
            (func.lower(User.username).like(prefix), 1),
            (func.lower(User.full_name).like(prefix), 2),
            else_=3,
        )
        ordered = statement.order_by(
            rank,
            User.full_name.asc(),
            User.id.asc(),
        )

    ordered = ordered.limit(limit).offset(offset)
    return list((await session.exec(ordered)).all())


@router.post("/conversations", response_model=StaffConversationRead)
async def start_conversation(
    payload: StaffConversationCreate,
    session: session_Dependency,
    staff: staff_dependency,
) -> StaffConversationRead:
    """Get or create a 1:1 conversation between the caller and a staff member.

    Idempotent on the participant pair: the same two people always map to one
    thread, whether the Owner, an admin or an agent starts it. A concurrent
    creator is resolved by re-reading the winner after a unique violation.
    """
    recipient = await eligible_recipient(
        session,
        sender=staff,
        recipient_user_id=payload.recipient_user_id,
    )

    conversation = await find_or_create_conversation(
        session,
        sender=staff,
        recipient=recipient,
        subject=payload.subject,
    )

    if conversation.id is None:  # pragma: no cover - defensive
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not open the conversation",
        )

    if conversation in session.new:
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            await session.refresh(staff)
            conversation = await find_or_create_conversation(
                session,
                sender=staff,
                recipient=recipient,
                subject=payload.subject,
            )
            await session.commit()
        await session.refresh(conversation)

    return await conversation_summary(session, conversation, staff)


@router.get("/conversations", response_model=list[StaffConversationRead])
async def list_conversations(
    session: session_Dependency,
    staff: staff_dependency,
    unread_only: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[StaffConversationRead]:
    """Every conversation the caller participates in, newest activity first.

    The list is scoped to the caller's participant columns, so no employee can
    ever see a thread they are not part of. ``unread_only`` keeps threads with
    at least one unread message addressed to the viewer.
    """
    statement = select(StaffConversation).where(
        or_(
            StaffConversation.participant_a_id == staff.id,
            StaffConversation.participant_b_id == staff.id,
        )
    )

    if unread_only:
        statement = statement.where(
            exists().where(
                StaffMessage.conversation_id == StaffConversation.id,
                StaffMessage.sender_user_id != staff.id,
                StaffMessage.read_at.is_(None),
            )
        )

    statement = (
        statement.order_by(
            func.coalesce(
                StaffConversation.last_message_at, StaffConversation.created_at
            ).desc(),
            StaffConversation.created_at.desc(),
            StaffConversation.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )
    conversations = list((await session.exec(statement)).all())
    return await conversation_summaries(session, conversations, staff)


@router.get("/conversations/{conversation_id}", response_model=StaffConversationDetail)
async def get_conversation(
    conversation_id: uuid.UUID,
    session: session_Dependency,
    staff: staff_dependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> StaffConversationDetail:
    conversation = await load_conversation(session, conversation_id, staff)

    messages = list(
        (
            await session.exec(
                select(StaffMessage)
                .where(StaffMessage.conversation_id == conversation.id)
                .order_by(StaffMessage.created_at.asc(), StaffMessage.id.asc())
                .limit(limit)
            )
        ).all()
    )

    return StaffConversationDetail(
        conversation=await conversation_summary(session, conversation, staff),
        messages=await _messages_with_mentions(session, messages),
    )


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=StaffMessageRead,
    status_code=status.HTTP_201_CREATED,
)
async def post_message(
    conversation_id: uuid.UUID,
    payload: StaffMessageCreate,
    session: session_Dependency,
    staff: staff_dependency,
    _rate_limit: Annotated[None, Depends(rate_limit("staff_message_create"))],
) -> StaffMessageRead:
    """Send a private message. Participants only; the recipient is derived
    from the conversation, never from the request body.

    Mentions are validated against real, active staff accounts before the
    message is written; an invalid mention aborts the whole send with a clear
    4xx rather than silently dropping it.
    """
    conversation = await load_conversation(session, conversation_id, staff)
    mentioned_user_ids = await validate_mentions(
        session, sender=staff, mentioned_user_ids=payload.mentioned_user_ids
    )

    message = send_message(
        session,
        conversation=conversation,
        sender=staff,
        body=payload.body,
        mentioned_user_ids=mentioned_user_ids,
    )
    await session.commit()
    await session.refresh(message)

    read = StaffMessageRead.model_validate(message)
    read.mentioned_user_ids = mentioned_user_ids
    return read


@router.post(
    "/conversations/{conversation_id}/read",
    response_model=MarkReadResult,
)
async def mark_read(
    conversation_id: uuid.UUID,
    session: session_Dependency,
    staff: staff_dependency,
) -> MarkReadResult:
    """Mark every message addressed to the caller as read."""
    conversation = await load_conversation(session, conversation_id, staff)

    updated = await mark_conversation_read(
        session, conversation=conversation, reader=staff
    )
    await session.commit()
    return MarkReadResult(updated=updated)
