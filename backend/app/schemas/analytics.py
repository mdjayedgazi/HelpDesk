from datetime import date, datetime

from pydantic import ConfigDict
from sqlmodel import SQLModel

from app.enums.enums import TicketCategory, TicketPriority, TicketStatus


class AnalyticsTotals(SQLModel):
    """Headline counters for the support operation."""

    model_config = ConfigDict(extra="forbid")

    total_tickets: int
    open_tickets: int
    """Tickets that are not RESOLVED or CLOSED — the live workload."""
    unassigned_tickets: int
    resolved_tickets: int
    closed_tickets: int
    urgent_open_tickets: int
    """URGENT tickets that are still OPEN or IN_PROGRESS."""
    total_users: int
    active_agents: int
    active_admins: int


class DailyTicketPoint(SQLModel):
    """One calendar day of ticket creation and resolution activity.

    Only days with at least one event are returned; the client fills the gaps
    so the series always spans a contiguous window.
    """

    model_config = ConfigDict(extra="forbid")

    day: date
    created: int
    resolved: int


class AgentWorkload(SQLModel):
    """Per-agent live workload. Sorted by active workload, then name."""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    full_name: str
    image_url: str | None
    active_tickets: int
    """Assigned tickets that are OPEN, IN_PROGRESS or WAITING_ON_CUSTOMER."""
    urgent_tickets: int
    """Assigned tickets with URGENT priority that are still active."""
    resolved_tickets: int
    """Assigned tickets that reached RESOLVED or CLOSED."""


class AnalyticsRead(SQLModel):
    """Aggregated support analytics.

    Every field is derived from existing rows with read-only aggregation; no
    schema, migration or business rule is involved. Any metric the backend
    cannot compute (for example SLA compliance) is simply absent rather than
    estimated.
    """

    model_config = ConfigDict(extra="forbid")

    generated_at: datetime
    window_days: int
    totals: AnalyticsTotals
    tickets_by_status: dict[TicketStatus, int]
    tickets_by_priority: dict[TicketPriority, int]
    tickets_by_category: dict[TicketCategory, int]
    daily: list[DailyTicketPoint]
    aging_over_7_days: int
    """Active tickets whose last update is older than seven days."""
    unassigned_over_24h: int
    """Unassigned tickets created more than 24 hours ago."""
    answered_without_resolution: int
    """Active tickets that are WAITING_ON_CUSTOMER."""
    agent_workload: list[AgentWorkload]
