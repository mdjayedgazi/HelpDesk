"""Owner Inbox internal messaging.

Two directions live here:

* the Owner composes a message to an *audience* (everyone / all agents / all
  admins / one employee) and reads the sent folder;
* an addressed AGENT/ADMIN reads the messages sent to them and marks them read.

Authorization (enforced in the backend, not only by hiding UI):

* compose, the recipient directory and the sent folder require the OWNER role
  (``owner_dependency``); an admin/agent/customer gets ``403``;
* a recipient can list and mark read only their own recipient rows; anybody
  else gets ``404`` for a message id they were not addressed in, so the API
  never reveals that another employee's message exists;
* the sender is always the authenticated user - the request body can never set
  it;
* customers cannot reach any endpoint here (``403`` from the role dependency).
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import String, cast, func, or_
from sqlmodel import select

from app.core.auth import owner_dependency, staff_dependency
from app.core.database import session_Dependency
from app.enums.enums import InternalAudience, Role
from app.models.internal_message import InternalMessage, InternalMessageRecipient
from app.models.user import User
from app.schemas.internal_messages import (
    InternalMessageCreate,
    InternalMessageDetail,
    InternalMessageReceived,
    InternalMessageRecipientRead,
    InternalMessageSummary,
)
from app.schemas.users import UserRead
from app.services.internal_messages import (
    ELIGIBLE_ROLES,
    PREVIEW_LENGTH,
    create_message,
    mark_message_read,
    resolve_recipients,
)

router = APIRouter(prefix="/api/v1/internal-messages", tags=["internal-messages"])


async def _read_counts(
    session, message_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    """Return {message_id: recipients_that_have_read} for the given messages."""
    if not message_ids:
        return {}
    rows = await session.exec(
        select(
            InternalMessageRecipient.message_id, func.count()
        )
        .where(
            InternalMessageRecipient.message_id.in_(message_ids),
            InternalMessageRecipient.read_at.is_not(None),
        )
        .group_by(InternalMessageRecipient.message_id)
    )
    return {message_id: count for message_id, count in rows.all()}


def _summary(
    message: InternalMessage, read_count: int
) -> InternalMessageSummary:
    return InternalMessageSummary(
        id=message.id,
        sender_user_id=message.sender_user_id,
        audience=message.audience,
        subject=message.subject,
        preview=message.body[:PREVIEW_LENGTH],
        recipient_count=message.recipient_count,
        read_count=read_count,
        created_at=message.created_at,
    )


@router.get("/recipients", response_model=list[UserRead])
async def search_recipients(
    session: session_Dependency,
    _owner: owner_dependency,
    q: Annotated[str | None, Query(max_length=120)] = None,
    role: Annotated[Role | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[User]:
    """Search the eligible employee directory (active agents/admins).

    Owner-only. Customers and the Owner are never returned. Search matches the
    display name, email, username, and the account id so an employee can always
    be told apart from a namesake without being looked up by hand.
    """
    if role is not None and role not in ELIGIBLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Recipients can only be agents or administrators",
        )
    roles = (role,) if role is not None else ELIGIBLE_ROLES

    statement = select(User).where(
        User.role.in_(roles), User.is_active.is_(True)
    )
    if q:
        like = f"%{q.lower()}%"
        statement = statement.where(
            or_(
                User.username.ilike(like),
                User.email.ilike(like),
                User.full_name.ilike(like),
                cast(User.id, String).ilike(like),
            )
        )

    statement = (
        statement.order_by(User.full_name.asc(), User.id.asc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.exec(statement)
    return list(result.all())


@router.post(
    "",
    response_model=InternalMessageSummary,
    status_code=status.HTTP_201_CREATED,
)
async def compose_message(
    payload: InternalMessageCreate,
    session: session_Dependency,
    owner: owner_dependency,
) -> InternalMessageSummary:
    """Compose and send an internal message. Owner-only.

    The audience is expanded to concrete, eligible recipients; an empty group
    is rejected (``409``) instead of silently succeeding. The message and every
    recipient row are written in one transaction.
    """
    recipients = await resolve_recipients(
        session,
        audience=payload.audience,
        recipient_user_id=payload.recipient_user_id,
    )

    message = create_message(
        session,
        sender=owner,
        audience=payload.audience,
        subject=payload.subject,
        body=payload.body,
        recipients=recipients,
    )
    await session.commit()
    await session.refresh(message)
    return _summary(message, read_count=0)


@router.get("/sent", response_model=list[InternalMessageSummary])
async def list_sent_messages(
    session: session_Dependency,
    owner: owner_dependency,
    audience: Annotated[InternalAudience | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=120)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[InternalMessageSummary]:
    """The Owner's sent messages, newest first, optionally filtered."""
    statement = select(InternalMessage).where(
        InternalMessage.sender_user_id == owner.id
    )
    if audience is not None:
        statement = statement.where(InternalMessage.audience == audience)
    if q:
        statement = statement.where(
            InternalMessage.subject.ilike(f"%{q.lower()}%")
        )

    statement = (
        statement.order_by(
            InternalMessage.created_at.desc(), InternalMessage.id.desc()
        )
        .limit(limit)
        .offset(offset)
    )
    messages = list((await session.exec(statement)).all())
    counts = await _read_counts(session, [m.id for m in messages])
    return [_summary(m, counts.get(m.id, 0)) for m in messages]


@router.get("/sent/{message_id}", response_model=InternalMessageDetail)
async def get_sent_message(
    message_id: uuid.UUID,
    session: session_Dependency,
    owner: owner_dependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> InternalMessageDetail:
    """One sent message with its body and a page of its recipient list."""
    message = await session.get(InternalMessage, message_id)
    if message is None or message.sender_user_id != owner.id:
        # Not the sender's message is a 404: the Sent folder only ever exposes
        # the Owner's own messages, and no endpoint lists other senders'.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found",
        )

    recipient_total = (
        await session.exec(
            select(func.count())
            .select_from(InternalMessageRecipient)
            .where(InternalMessageRecipient.message_id == message.id)
        )
    ).one()

    recipients = (
        await session.exec(
            select(InternalMessageRecipient)
            .where(InternalMessageRecipient.message_id == message.id)
            .order_by(
                InternalMessageRecipient.recipient_full_name_snapshot.asc(),
                InternalMessageRecipient.id.asc(),
            )
            .limit(limit)
            .offset(offset)
        )
    ).all()

    read_count = (
        await session.exec(
            select(func.count())
            .select_from(InternalMessageRecipient)
            .where(
                InternalMessageRecipient.message_id == message.id,
                InternalMessageRecipient.read_at.is_not(None),
            )
        )
    ).one()

    return InternalMessageDetail(
        id=message.id,
        sender_user_id=message.sender_user_id,
        audience=message.audience,
        subject=message.subject,
        body=message.body,
        recipient_count=message.recipient_count,
        read_count=read_count,
        created_at=message.created_at,
        recipient_total=recipient_total,
        recipients=[
            InternalMessageRecipientRead.model_validate(r) for r in recipients
        ],
    )


@router.get("/received", response_model=list[InternalMessageReceived])
async def list_received_messages(
    session: session_Dependency,
    staff: staff_dependency,
    is_read: Annotated[bool | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[InternalMessageReceived]:
    """Messages addressed to the caller. An employee only ever sees their own.

    The Owner is not a recipient of these messages, so the Owner simply gets an
    empty list; a customer is rejected by the role dependency (``403``).
    """
    statement = (
        select(InternalMessageRecipient, InternalMessage, User)
        .join(
            InternalMessage,
            InternalMessage.id == InternalMessageRecipient.message_id,
        )
        .join(User, User.id == InternalMessage.sender_user_id)
        .where(InternalMessageRecipient.recipient_user_id == staff.id)
    )
    if is_read is True:
        statement = statement.where(
            InternalMessageRecipient.read_at.is_not(None)
        )
    elif is_read is False:
        statement = statement.where(InternalMessageRecipient.read_at.is_(None))

    statement = (
        statement.order_by(
            InternalMessage.created_at.desc(), InternalMessage.id.desc()
        )
        .limit(limit)
        .offset(offset)
    )

    rows = (await session.exec(statement)).all()
    return [
        InternalMessageReceived(
            id=message.id,
            sender_user_id=message.sender_user_id,
            sender_full_name=sender.full_name,
            audience=message.audience,
            subject=message.subject,
            body=message.body,
            created_at=message.created_at,
            read_at=recipient.read_at,
        )
        for recipient, message, sender in rows
    ]


@router.post("/{message_id}/read", response_model=dict[str, int])
async def mark_received_message_read(
    message_id: uuid.UUID,
    session: session_Dependency,
    staff: staff_dependency,
) -> dict[str, int]:
    """Mark the caller's own recipient row as read."""
    updated = await mark_message_read(
        session, message_id=message_id, reader=staff
    )
    await session.commit()
    return {"updated": updated}
