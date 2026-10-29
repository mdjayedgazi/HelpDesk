"""Private messaging between staff (AGENT/ADMIN) and the Owner.

Authorization summary (enforced here, in the backend, not just in the UI):

* every endpoint requires a staff role via ``staff_dependency`` - a CUSTOMER
  receives ``403`` from the dependency and can never read, start, or send in a
  private conversation;
* only AGENT/ADMIN may *start* a conversation; the Owner answers from the
  inbox;
* reading, replying and marking read all require being a participant of that
  specific conversation; anybody else gets ``404`` (an agent cannot even
  discover that another agent's thread exists).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import exists, func
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
from app.services.staff_messages import (
    conversation_summaries,
    conversation_summary,
    get_owner,
    load_conversation,
    mark_conversation_read,
    send_message,
)

router = APIRouter(prefix="/api/v1/staff-messages", tags=["staff-messages"])


@router.post("/conversations", response_model=StaffConversationRead)
async def start_conversation(
    payload: StaffConversationCreate,
    session: session_Dependency,
    staff: staff_dependency,
) -> StaffConversationRead:
    """Get or create the caller's private conversation with the Owner.

    Idempotent: an AGENT/ADMIN has exactly one thread with the Owner, so
    calling this again returns the existing conversation instead of creating a
    duplicate. The Owner does not start conversations (there is one thread per
    staff member; the Owner replies inside them).
    """
    if staff.role not in (Role.AGENT, Role.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only agents and admins start conversations with the Owner",
        )

    owner = await get_owner(session)

    conversation = (
        await session.exec(
            select(StaffConversation).where(StaffConversation.staff_user_id == staff.id)
        )
    ).first()

    if conversation is None:
        conversation = StaffConversation(
            staff_user_id=staff.id,
            owner_user_id=owner.id,
            subject=payload.subject or f"Conversation with {staff.full_name}",
        )
        session.add(conversation)
        try:
            await session.commit()
        except IntegrityError:
            # A concurrent request created the same thread (unique index on
            # staff_user_id). Return the winner instead of failing.
            await session.rollback()
            await session.refresh(staff)
            conversation = (
                await session.exec(
                    select(StaffConversation).where(
                        StaffConversation.staff_user_id == staff.id
                    )
                )
            ).first()
            if conversation is None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Could not open the conversation",
                ) from None
        else:
            await session.refresh(conversation)

    return await conversation_summary(session, conversation, staff)


@router.get("/conversations", response_model=list[StaffConversationRead])
async def list_conversations(
    session: session_Dependency,
    staff: staff_dependency,
    staff_role: Annotated[Role | None, Query()] = None,
    staff_user_id: Annotated[uuid.UUID | None, Query()] = None,
    unread_only: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[StaffConversationRead]:
    """AGENT/ADMIN: their own thread. OWNER: the whole inbox.

    The Owner inbox additionally supports the filters the UI exposes: by the
    staff participant's role, by one specific sender, and by unread threads.
    Those two sender filters are applied for the Owner view only (an agent is
    already scoped to their own single thread). The result is paginated and
    summaries are built in bulk to avoid N+1 queries.
    """
    if staff.role == Role.OWNER:
        statement = select(StaffConversation)

        if staff_role is not None:
            staff_ids = (
                await session.exec(select(User.id).where(User.role == staff_role))
            ).all()
            statement = statement.where(StaffConversation.staff_user_id.in_(staff_ids))
        if staff_user_id is not None:
            statement = statement.where(
                StaffConversation.staff_user_id == staff_user_id
            )
    else:
        statement = select(StaffConversation).where(
            StaffConversation.staff_user_id == staff.id
        )

    if unread_only:
        # Keep only threads that contain a message addressed to the viewer that
        # has not been read yet.
        statement = statement.where(
            exists().where(
                StaffMessage.conversation_id == StaffConversation.id,
                StaffMessage.sender_user_id != staff.id,
                StaffMessage.read_at.is_(None),
            )
        )

    statement = (
        statement.order_by(
            # Conversations without messages yet fall back to their creation time
            # so the inbox ordering is stable and portable (works on SQLite too).
            func.coalesce(
                StaffConversation.last_message_at, StaffConversation.created_at
            ).desc(),
            StaffConversation.created_at.desc(),
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

    messages = (
        await session.exec(
            select(StaffMessage)
            .where(StaffMessage.conversation_id == conversation.id)
            .order_by(StaffMessage.created_at.asc(), StaffMessage.id.asc())
            .limit(limit)
        )
    ).all()

    return StaffConversationDetail(
        conversation=await conversation_summary(session, conversation, staff),
        messages=[StaffMessageRead.model_validate(m) for m in messages],
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
    from the conversation, never from the request body."""
    conversation = await load_conversation(session, conversation_id, staff)

    message = send_message(
        session, conversation=conversation, sender=staff, body=payload.body
    )
    await session.commit()
    await session.refresh(message)
    return StaffMessageRead.model_validate(message)


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
