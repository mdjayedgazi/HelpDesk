import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from sqlmodel import select

from app.core.auth import staff_dependency
from app.core.database import session_Dependency
from app.models.ticketHistory import TicketHistory
from app.schemas.ticketHistorys import TicketHistoryRead
from app.services.tickets import load_visible_ticket

router = APIRouter(
    prefix="/api/v1/tickets/{ticket_id}/history",
    tags=["ticket-history"],
)


@router.get("", response_model=list[TicketHistoryRead])
async def list_ticket_history(
    ticket_id: uuid.UUID,
    session: session_Dependency,
    staff: staff_dependency,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TicketHistory]:
    """Return the internal audit trail for a ticket.

    Staff only: the history can contain internal events, so customers never
    reach this endpoint even for tickets they own. Staff still only see the
    history of tickets they are allowed to view (``load_visible_ticket``).
    """
    await load_visible_ticket(session, ticket_id, staff)

    statement = (
        select(TicketHistory)
        .where(TicketHistory.ticket_id == ticket_id)
        .order_by(TicketHistory.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.exec(statement)
    return list(result.all())
