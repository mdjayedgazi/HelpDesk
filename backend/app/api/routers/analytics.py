from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter
from sqlalchemy import func
from sqlmodel import select

from app.core.auth import admin_dependency
from app.core.database import session_Dependency
from app.enums.enums import Role, TicketCategory, TicketPriority, TicketStatus
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.analytics import (
    AgentWorkload,
    AnalyticsRead,
    AnalyticsTotals,
    DailyTicketPoint,
)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

# Active work is anything the team still has to act on.
ACTIVE_STATUSES = (
    TicketStatus.OPEN,
    TicketStatus.IN_PROGRESS,
    TicketStatus.WAITING_ON_CUSTOMER,
)
RESOLVED_STATUSES = (TicketStatus.RESOLVED, TicketStatus.CLOSED)
DEFAULT_WINDOW_DAYS = 14
AGING_AFTER = timedelta(days=7)
UNASSIGNED_GRACE = timedelta(hours=24)


def _as_date(value: object) -> date:
    """Normalize a grouped SQL date value.

    PostgreSQL returns a ``date``; SQLite returns the ``YYYY-MM-DD`` string that
    ``date()`` produced. Both become a real ``date`` here.
    """
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


@router.get("/analytics", response_model=AnalyticsRead)
async def get_analytics(
    session: session_Dependency,
    _admin: admin_dependency,
) -> AnalyticsRead:
    """Aggregated, read-only support analytics for the admin/owner dashboard.

    This endpoint only *reads* existing rows with aggregate queries. It adds no
    table, column, migration or business rule; it exists so the dashboard can
    visualize real data instead of inventing metrics. Anything that cannot be
    derived from stored timestamps (for example SLA compliance) is deliberately
    omitted.
    """
    now = datetime.now(UTC)
    window_days = DEFAULT_WINDOW_DAYS
    since = now - timedelta(days=window_days - 1)
    since_day = since.date()

    # Status and priority totals -------------------------------------------
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

    category_rows = await session.exec(
        select(Ticket.category, func.count()).group_by(Ticket.category)
    )
    tickets_by_category = dict.fromkeys(TicketCategory, 0)
    for ticket_category, count in category_rows.all():
        tickets_by_category[ticket_category] = count

    # Daily volume: creations and resolutions inside the window -------------
    created_rows = await session.exec(
        select(func.date(Ticket.created_at), func.count())
        .where(Ticket.created_at >= since)
        .group_by(func.date(Ticket.created_at))
    )
    resolved_rows = await session.exec(
        select(func.date(Ticket.resolved_at), func.count())
        .where(Ticket.resolved_at.is_not(None), Ticket.resolved_at >= since)
        .group_by(func.date(Ticket.resolved_at))
    )

    created_by_day = {_as_date(day): count for day, count in created_rows.all() if day}
    resolved_by_day = {
        _as_date(day): count for day, count in resolved_rows.all() if day
    }

    daily: list[DailyTicketPoint] = []
    for offset in range(window_days):
        day = since_day + timedelta(days=offset)
        daily.append(
            DailyTicketPoint(
                day=day,
                created=created_by_day.get(day, 0),
                resolved=resolved_by_day.get(day, 0),
            )
        )

    # Queue health ---------------------------------------------------------
    unassigned = (
        await session.exec(
            select(func.count())
            .select_from(Ticket)
            .where(
                Ticket.assignee_user_id.is_(None), Ticket.status.in_(ACTIVE_STATUSES)
            )
        )
    ).one()

    unassigned_over_24h = (
        await session.exec(
            select(func.count())
            .select_from(Ticket)
            .where(
                Ticket.assignee_user_id.is_(None),
                Ticket.status.in_(ACTIVE_STATUSES),
                Ticket.created_at <= now - UNASSIGNED_GRACE,
            )
        )
    ).one()

    aging_over_7_days = (
        await session.exec(
            select(func.count())
            .select_from(Ticket)
            .where(
                Ticket.status.in_(ACTIVE_STATUSES),
                Ticket.updated_at <= now - AGING_AFTER,
            )
        )
    ).one()

    urgent_open = (
        await session.exec(
            select(func.count())
            .select_from(Ticket)
            .where(
                Ticket.priority == TicketPriority.URGENT,
                Ticket.status.in_((TicketStatus.OPEN, TicketStatus.IN_PROGRESS)),
            )
        )
    ).one()

    # People ---------------------------------------------------------------
    total_users = (await session.exec(select(func.count()).select_from(User))).one()
    active_agents = (
        await session.exec(
            select(func.count())
            .select_from(User)
            .where(User.role == Role.AGENT, User.is_active.is_(True))
        )
    ).one()
    active_admins = (
        await session.exec(
            select(func.count())
            .select_from(User)
            .where(
                User.role.in_((Role.ADMIN, Role.OWNER)),
                User.is_active.is_(True),
            )
        )
    ).one()

    # Per-agent workload ---------------------------------------------------
    workload_rows = await session.exec(
        select(
            Ticket.assignee_user_id,
            Ticket.status,
            Ticket.priority,
            func.count(),
        )
        .where(Ticket.assignee_user_id.is_not(None))
        .group_by(Ticket.assignee_user_id, Ticket.status, Ticket.priority)
    )

    per_agent: dict[str, dict[str, int]] = defaultdict(
        lambda: {"active": 0, "urgent": 0, "resolved": 0}
    )
    for assignee_id, ticket_status, ticket_priority, count in workload_rows.all():
        if assignee_id is None:
            continue
        key = str(assignee_id)
        if ticket_status in ACTIVE_STATUSES:
            per_agent[key]["active"] += count
            if ticket_priority == TicketPriority.URGENT:
                per_agent[key]["urgent"] += count
        else:
            per_agent[key]["resolved"] += count

    agents = (
        await session.exec(
            select(User).where(User.role == Role.AGENT, User.is_active.is_(True))
        )
    ).all()

    agent_workload = [
        AgentWorkload(
            user_id=str(agent.id),
            full_name=agent.full_name,
            image_url=agent.image_url,
            active_tickets=per_agent[str(agent.id)]["active"],
            urgent_tickets=per_agent[str(agent.id)]["urgent"],
            resolved_tickets=per_agent[str(agent.id)]["resolved"],
        )
        for agent in agents
    ]
    agent_workload.sort(
        key=lambda entry: (-entry.active_tickets, entry.full_name.lower())
    )

    totals = AnalyticsTotals(
        total_tickets=sum(tickets_by_status.values()),
        open_tickets=tickets_by_status[TicketStatus.OPEN]
        + tickets_by_status[TicketStatus.IN_PROGRESS],
        unassigned_tickets=unassigned,
        resolved_tickets=tickets_by_status[TicketStatus.RESOLVED],
        closed_tickets=tickets_by_status[TicketStatus.CLOSED],
        urgent_open_tickets=urgent_open,
        total_users=total_users,
        active_agents=active_agents,
        active_admins=active_admins,
    )

    return AnalyticsRead(
        generated_at=now,
        window_days=window_days,
        totals=totals,
        tickets_by_status=tickets_by_status,
        tickets_by_priority=tickets_by_priority,
        tickets_by_category=tickets_by_category,
        daily=daily,
        aging_over_7_days=aging_over_7_days,
        unassigned_over_24h=unassigned_over_24h,
        answered_without_resolution=tickets_by_status[TicketStatus.WAITING_ON_CUSTOMER],
        agent_workload=agent_workload,
    )
