"""Account-management (admin escalation) requests.

Workflow
--------
An AGENT who needs a privileged account action (recovery, identity relinking,
protected profile correction, role/status change) opens a structured request.
An ADMIN may open one too. The target account is derived server-side:

* from a ticket the requester can already see (the target is the ticket's
  requester), and/or
* for ADMINs, from the user directory (``target_user_id``).

Authorized ADMIN/OWNER staff review the request and move it through
``PENDING -> IN_REVIEW -> APPROVED/REJECTED`` and, once approved,
``-> COMPLETED``. A decision always records who made it; a rejection always
requires a reason. The creator can never decide their own request.

Identity safety
---------------
This API never accepts a new Clerk id, email, local primary key, or role as
part of an escalation: approving a request is an authorization decision, and
the actual identity change must be performed through the supported, separately
audited Clerk process. Every status change is appended to the request's event
trail.
"""

import uuid
from datetime import datetime, timezone, UTC
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import select

from app.core.auth import admin_dependency, staff_dependency
from app.core.database import session_Dependency
from app.enums.enums import (
    EscalationCategory,
    EscalationStatus,
    NotificationType,
    Role,
)
from app.models.account_request import (
    AccountManagementRequest,
    AccountRequestComment,
    AccountRequestEvent,
)
from app.models.user import User
from app.schemas.account_requests import (
    AccountRequestCommentCreate,
    AccountRequestCommentRead,
    AccountRequestCreate,
    AccountRequestDetail,
    AccountRequestEventRead,
    AccountRequestRead,
    AccountRequestStatusUpdate,
)
from app.services.account_requests import (
    COMMENTABLE_ESCALATION_STATUSES,
    load_visible_request,
    notify_creator,
    notify_reviewers,
    record_request_event,
    validate_escalation_transition,
)
from app.services.tickets import load_visible_ticket

router = APIRouter(prefix="/api/v1/account-requests", tags=["account-requests"])


@router.post("", response_model=AccountRequestRead, status_code=status.HTTP_201_CREATED)
async def create_account_request(
    payload: AccountRequestCreate,
    session: session_Dependency,
    staff: staff_dependency,
) -> AccountManagementRequest:
    """Open an account-management request for review."""
    if staff.role not in (Role.AGENT, Role.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only agents and admins can open account requests",
        )

    ticket = None
    target: User | None = None

    if payload.ticket_id is not None:
        # Reuses the ticket visibility rule: an agent can only escalate about a
        # ticket they already work on (assigned to them or in the open queue).
        ticket = await load_visible_ticket(session, payload.ticket_id, staff)
        target = await session.get(User, ticket.created_by_user_id)
        if target is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="The ticket's requester no longer exists",
            )

    if staff.role == Role.AGENT:
        # Agents cannot name an arbitrary account: the target always comes from
        # the related ticket. If they repeat the ticket requester explicitly it
        # must match.
        if ticket is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Agents must reference a ticket",
            )
        if payload.target_user_id is not None and payload.target_user_id != target.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Agents cannot choose the target account",
            )
    elif payload.target_user_id is not None:
        candidate = await session.get(User, payload.target_user_id)
        if candidate is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target user not found",
            )
        if target is not None and target.id != candidate.id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="The target user does not match the ticket requester",
            )
        target = candidate

    if target is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Provide a related ticket or a target user",
        )

    if target.role == Role.OWNER:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The Owner account cannot be the target of a request",
        )

    request = AccountManagementRequest(
        target_user_id=target.id,
        target_full_name_snapshot=target.full_name,
        target_email_snapshot=target.email,
        ticket_id=ticket.id if ticket is not None else None,
        category=payload.category,
        justification=payload.justification,
        internal_details=payload.internal_details,
        created_by_user_id=staff.id,
    )
    session.add(request)

    record_request_event(
        session,
        request=request,
        actor=staff,
        event_type="REQUEST_CREATED",
        old_value=None,
        new_value={
            "status": EscalationStatus.PENDING.value,
            "category": payload.category.value,
            "ticket_id": str(ticket.id) if ticket is not None else None,
        },
    )
    await notify_reviewers(session, request=request, actor=staff)

    await session.commit()
    await session.refresh(request)
    return request


@router.get("", response_model=list[AccountRequestRead])
async def list_account_requests(
    session: session_Dependency,
    staff: staff_dependency,
    status_filter: Annotated[EscalationStatus | None, Query(alias="status")] = None,
    category: Annotated[EscalationCategory | None, Query()] = None,
    mine: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AccountManagementRequest]:
    """List requests visible to the caller.

    Agents only ever see the requests they created. Admins and the Owner see
    the whole queue (``mine=true`` narrows it to their own).
    """
    statement = select(AccountManagementRequest)

    if staff.role == Role.AGENT or mine:
        statement = statement.where(
            AccountManagementRequest.created_by_user_id == staff.id
        )

    if status_filter is not None:
        statement = statement.where(AccountManagementRequest.status == status_filter)
    if category is not None:
        statement = statement.where(AccountManagementRequest.category == category)

    statement = (
        statement.order_by(AccountManagementRequest.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.exec(statement)
    return list(result.all())


@router.get("/{request_id}", response_model=AccountRequestDetail)
async def get_account_request(
    request_id: uuid.UUID,
    session: session_Dependency,
    staff: staff_dependency,
) -> AccountRequestDetail:
    request = await load_visible_request(session, request_id, staff)

    comments = (
        await session.exec(
            select(AccountRequestComment)
            .where(AccountRequestComment.request_id == request.id)
            .order_by(
                AccountRequestComment.created_at.asc(),
                AccountRequestComment.id.asc(),
            )
        )
    ).all()
    events = (
        await session.exec(
            select(AccountRequestEvent)
            .where(AccountRequestEvent.request_id == request.id)
            .order_by(
                AccountRequestEvent.created_at.asc(), AccountRequestEvent.id.asc()
            )
        )
    ).all()

    return AccountRequestDetail(
        request=AccountRequestRead.model_validate(request),
        comments=[AccountRequestCommentRead.model_validate(c) for c in comments],
        events=[AccountRequestEventRead.model_validate(e) for e in events],
    )


@router.post(
    "/{request_id}/comments",
    response_model=AccountRequestCommentRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_account_request_comment(
    request_id: uuid.UUID,
    payload: AccountRequestCommentCreate,
    session: session_Dependency,
    staff: staff_dependency,
) -> AccountRequestComment:
    """Add an internal comment (creator and authorized staff only)."""
    request = await load_visible_request(session, request_id, staff)

    if request.status not in COMMENTABLE_ESCALATION_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This request is closed for further comments",
        )

    comment = AccountRequestComment(
        request_id=request.id,
        author_user_id=staff.id,
        body=payload.body,
    )
    session.add(comment)

    if request.created_by_user_id == staff.id:
        # The requester added context: alert the reviewers.
        await notify_reviewers(
            session,
            request=request,
            actor=staff,
            type=NotificationType.ESCALATION_UPDATED,
            title="Account request updated",
            message=(
                "The requester added new information to an account-management request."
            ),
        )
    else:
        notify_creator(
            session,
            request=request,
            actor=staff,
            title="Update on your account request",
            message="There is new activity on your account-management request.",
        )

    await session.commit()
    await session.refresh(comment)
    return comment


@router.post("/{request_id}/status", response_model=AccountRequestRead)
async def update_account_request_status(
    request_id: uuid.UUID,
    payload: AccountRequestStatusUpdate,
    session: session_Dependency,
    reviewer: admin_dependency,
) -> AccountManagementRequest:
    """Review/approve/reject/complete a request. ADMIN/OWNER only.

    The state machine only allows forward transitions, a rejection must carry a
    reason, and the creator can never decide their own request. Nothing here
    changes the target account: approving is an authorization decision that a
    human then performs through the supported identity process.
    """
    request = await load_visible_request(session, request_id, reviewer)

    if request.created_by_user_id == reviewer.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot decide on your own request",
        )

    new_status = payload.status
    validate_escalation_transition(request.status, new_status)

    if new_status == EscalationStatus.REJECTED and payload.reason is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="A rejection reason is required",
        )

    old_status = request.status
    now = datetime.now(UTC)

    if new_status in (EscalationStatus.APPROVED, EscalationStatus.REJECTED):
        request.decided_by_user_id = reviewer.id
        request.decided_at = now
        request.decision_reason = payload.reason
    elif new_status == EscalationStatus.COMPLETED:
        request.completed_by_user_id = reviewer.id
        request.completed_at = now

    request.status = new_status
    session.add(request)

    record_request_event(
        session,
        request=request,
        actor=reviewer,
        event_type="STATUS_CHANGED",
        old_value={"status": old_status.value},
        new_value={
            "status": new_status.value,
            **({"reason": payload.reason} if payload.reason else {}),
        },
    )

    notify_creator(
        session,
        request=request,
        actor=reviewer,
        title="Your account request was updated",
        message=f"Your account-management request is now {new_status.value}.",
    )

    await session.commit()
    await session.refresh(request)
    return request
