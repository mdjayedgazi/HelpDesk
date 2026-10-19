from pydantic import ConfigDict
from sqlmodel import SQLModel

from app.enums.enums import TicketPriority, TicketStatus


class DashboardRead(SQLModel):
    model_config = ConfigDict(extra="forbid")

    total_tickets: int
    tickets_by_status: dict[TicketStatus, int]
    tickets_by_priority: dict[TicketPriority, int]
    total_users: int
    active_agents: int
