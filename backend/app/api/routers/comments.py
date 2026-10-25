import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import select

from app.core.auth import user_dependency
from app.core.database import session_Dependency
from app.core.rate_limit import rate_limit
from app.enums.enums import NotificationType, Role
from app.models.comment import Comment
from app.schemas.comments import CommentCreate, CommentRead, PublicCommentRead
from app.services.notifications import active_admin_ids, notify_many
from app.services.tickets import load_visible_ticket, record_history

router = APIRouter(
    prefix="/api/v1/tickets/{ticket_id}/comments",
    tags=["comments"],
)


@router.get("", response_model=list[CommentRead | PublicCommentRead])
async def list_comments(
    ticket_id: uuid.UUID,
    session: session_Dependency,
    user: user_dependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CommentRead | PublicCommentRead]:
    """List a ticket's comments.

    Customers never see internal notes; staff see everything.
    """
    await load_visible_ticket(session, ticket_id, user)

    statement = (
        select(Comment)
        .where(Comment.ticket_id == ticket_id)
        .order_by(Comment.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    if user.role == Role.CUSTOMER:
        statement = statement.where(Comment.is_internal.is_(False))

    result = await session.exec(statement)
    comments = list(result.all())

    if user.role == Role.CUSTOMER:
        return [PublicCommentRead.model_validate(c) for c in comments]
    return [CommentRead.model_validate(c) for c in comments]


@router.post(
    "",
    response_model=CommentRead | PublicCommentRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_comment(
    ticket_id: uuid.UUID,
    payload: CommentCreate,
    session: session_Dependency,
    user: user_dependency,
    _rate_limit: Annotated[None, Depends(rate_limit("comment_create"))],
) -> CommentRead | PublicCommentRead:
    """Add a comment or, for staff, an internal note."""
    ticket = await load_visible_ticket(session, ticket_id, user)

    if payload.is_internal and user.role == Role.CUSTOMER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff can create internal notes",
        )

    comment = Comment(
        ticket_id=ticket.id,
        author_user_id=user.id,
        body=payload.body,
        is_internal=payload.is_internal,
    )
    session.add(comment)

    await _notify_comment_recipients(
        session, ticket=ticket, author=user, comment=comment
    )

    # Only public comments appear in the history customers can read.
    if not payload.is_internal:
        record_history(
            session,
            ticket=ticket,
            actor=user,
            event_type="COMMENT_ADDED",
            new_value=None,
        )

    await session.commit()
    await session.refresh(comment)

    if user.role == Role.CUSTOMER:
        return PublicCommentRead.model_validate(comment)
    return CommentRead.model_validate(comment)


async def _notify_comment_recipients(session, *, ticket, author, comment) -> None:
    """Notify the people involved in the ticket, never the author.

    A public comment goes to the customer and the assignee. When nobody is
    assigned yet, the administrative queue is told instead of the ticket
    silently waiting: a public update on an unassigned ticket is exactly the
    kind of work that needs to be picked up. An internal note is staff-only and
    never reaches a customer.
    """
    recipients: set[uuid.UUID] = set()

    if comment.is_internal:
        if ticket.assignee_user_id is not None:
            recipients.add(ticket.assignee_user_id)
    else:
        recipients.add(ticket.created_by_user_id)
        if ticket.assignee_user_id is not None:
            recipients.add(ticket.assignee_user_id)
        else:
            recipients |= await active_admin_ids(session)

    recipients.discard(author.id)

    notify_many(
        session,
        recipient_ids=recipients,
        type=NotificationType.NEW_COMMENT,
        title="New comment on a ticket",
        message=f"A new comment was added to ticket #{ticket.ticket_number}.",
        related_ticket_id=ticket.id,
    )
