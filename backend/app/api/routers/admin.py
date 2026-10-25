from fastapi import APIRouter
from sqlalchemy import func
from sqlmodel import select

from app.core.auth import admin_dependency
from app.core.database import session_Dependency
from app.enums.enums import Role, TicketPriority, TicketStatus
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.admin import DashboardRead
from app.schemas.users import UserRead

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.get("/dashboard", response_model=DashboardRead)
async def get_dashboard(
    session: session_Dependency,
    _admin: admin_dependency,
) -> DashboardRead:
    """Aggregate numbers for the admin dashboard."""
    total_tickets = (await session.exec(select(func.count()).select_from(Ticket))).one()

    status_rows = await session.exec(
        select(Ticket.status, func.count()).group_by(Ticket.status)
    )
    tickets_by_status = dict.fromkeys(TicketStatus, 0)
    for ticket_status, count in status_rows.all():
        tickets_by_status[ticket_status] = count

    priority_rows = await session.exec(
        select(Ticket.priority, func.count()).group_by(Ticket.priority)
    )
    tickets_by_priority = dict.fromkeys(TicketPriority, 0)
    for ticket_priority, count in priority_rows.all():
        tickets_by_priority[ticket_priority] = count

    total_users = (await session.exec(select(func.count()).select_from(User))).one()

    active_agents = (
        await session.exec(
            select(func.count())
            .select_from(User)
            .where(User.role == Role.AGENT, User.is_active.is_(True))
        )
    ).one()

    return DashboardRead(
        total_tickets=total_tickets,
        tickets_by_status=tickets_by_status,
        tickets_by_priority=tickets_by_priority,
        total_users=total_users,
        active_agents=active_agents,
    )


@router.get("/agents", response_model=list[UserRead])
async def list_assignable_agents(
    session: session_Dependency,
    _admin: admin_dependency,
) -> list[User]:
    """Active agents that a ticket may be assigned to."""
    statement = (
        select(User)
        .where(User.role == Role.AGENT, User.is_active.is_(True))
        .order_by(User.full_name.asc())
    )
    result = await session.exec(statement)
    return list(result.all())
