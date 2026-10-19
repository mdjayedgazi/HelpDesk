"""Workload-aware, deterministic automatic ticket assignment.

The service picks *one* eligible AGENT for a new ticket using current database
records only (never frontend input, never randomness).

Eligibility
-----------
Only active local users with the ``AGENT`` role are eligible. Inactive agents,
customers, admins and the Owner are excluded. The chosen agent is re-read under
a row lock and re-verified before the assignment is persisted, so a concurrent
deactivation or role change cannot race an assignment.

Scoring (documented contract, mirrored in ``data.md``)
------------------------------------------------------
1. **Weighted unresolved workload** (ascending). Only tickets in the current
   unresolved statuses count (``OPEN``, ``IN_PROGRESS``,
   ``WAITING_ON_CUSTOMER``); ``RESOLVED``/``CLOSED`` tickets are complete work
   and contribute nothing. Each unresolved ticket is weighted by its priority:
   LOW=1, NORMAL=2, HIGH=4, URGENT=8.
2. **Fairness rotation** (ascending ``last assigned``): the agent whose most
   recent assignment happened longest ago wins. An agent who has never been
   assigned sorts first (``NULL`` first).
3. **Recent resolution speed** (ascending median resolution time): only applied
   when steps 1 and 2 tie *and* the agent has at least
   ``MIN_RESOLVED_FOR_SPEED`` tickets resolved within
   ``RECENT_WINDOW_DAYS``. Resolution time is measured from assignment
   (``assigned_at``, falling back to ``created_at``) to ``resolved_at``.
   Agents without reliable history sort after measured agents, so speed can
   never override workload or fairness.
4. **Stable rotation** (ascending agent UUID): the final deterministic
   tie-break with no randomness.

Concurrency
-----------
``acquire_assignment_lock`` takes a PostgreSQL transaction-level advisory lock,
so two simultaneous creations cannot both make a decision from stale workload
data: the second waits for the first to commit and then sees the new ticket.
SQLite (used by the unit tests) serialises writers itself and needs no extra
lock. No network request is ever made while the lock is held.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, text
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.enums.enums import Role, TicketPriority, TicketStatus
from app.models.ticket import Ticket
from app.models.user import User

logger = logging.getLogger(__name__)

# Tickets in these statuses are work in progress and count toward workload.
UNRESOLVED_STATUSES: tuple[TicketStatus, ...] = (
    TicketStatus.OPEN,
    TicketStatus.IN_PROGRESS,
    TicketStatus.WAITING_ON_CUSTOMER,
)

# Relative weight of one unresolved ticket per priority. Urgent work is worth
# 4x normal work; low-priority work half. Doubling keeps the numbers small,
# explainable and stable for reporting.
PRIORITY_WEIGHTS: dict[TicketPriority, int] = {
    TicketPriority.LOW: 1,
    TicketPriority.NORMAL: 2,
    TicketPriority.HIGH: 4,
    TicketPriority.URGENT: 8,
}

# Recent-resolution performance is only consulted for agents with at least this
# many tickets resolved inside the window. Below the threshold the data is not
# considered reliable and the agent is treated as "no measurement".
RECENT_WINDOW_DAYS = 90
MIN_RESOLVED_FOR_SPEED = 3

# Stable key for the PostgreSQL advisory lock; any constant works as long as it
# is unique within this application.
_ASSIGNMENT_LOCK_KEY = 0x48444B41  # "HDKA"


@dataclass(frozen=True)
class AgentWorkload:
    """Current assignment inputs for one eligible agent."""

    agent_id: uuid.UUID
    weighted_load: int
    active_tickets: int
    last_assigned_at: datetime | None
    median_resolution_seconds: int | None
    resolved_sample_size: int

    @property
    def rank_key(self) -> tuple:
        """Total ordering implementing the documented scoring contract."""
        return (
            self.weighted_load,
            _timestamp(self.last_assigned_at, default=float("-inf")),
            self.median_resolution_seconds
            if self.median_resolution_seconds is not None
            else float("inf"),
            str(self.agent_id),
        )


@dataclass(frozen=True)
class AssignmentDecision:
    agent_id: uuid.UUID
    reason: str
    weighted_load: int
    active_tickets: int
    considered_agents: int
    eligible_agents: int


def _timestamp(value: datetime | None, *, default: float) -> float:
    """Seconds since epoch, treating naive timestamps as UTC.

    PostgreSQL returns timezone-aware datetimes; SQLite (the unit-test
    database) returns naive ones. Converting both the same way keeps the
    ordering deterministic on either backend.
    """
    if value is None:
        return default
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def priority_weight(priority: TicketPriority) -> int:
    return PRIORITY_WEIGHTS.get(priority, PRIORITY_WEIGHTS[TicketPriority.NORMAL])


def _priority_case():
    """SQL CASE expression computing the weight of a ticket row."""
    return case(
        *(
            (Ticket.priority == priority, weight)
            for priority, weight in PRIORITY_WEIGHTS.items()
        ),
        else_=0,
    )


async def acquire_assignment_lock(session: AsyncSession) -> None:
    """Serialise assignment decisions for the current transaction.

    On PostgreSQL this is a transaction-level advisory lock: it is released
    automatically when the transaction commits or rolls back. Holding it means
    the workload snapshot used to pick an agent is stable and the next request
    observes this request's committed ticket. SQLite serialises writers itself,
    so the tests need no extra lock.
    """
    bind = session.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        await session.exec(
            text("SELECT pg_advisory_xact_lock(:key)"),
            params={"key": _ASSIGNMENT_LOCK_KEY},
        )


async def workload_for_agents(
    session: AsyncSession, agent_ids: list[uuid.UUID]
) -> dict[uuid.UUID, AgentWorkload]:
    """Return the current workload of every id in ``agent_ids``."""
    workloads: dict[uuid.UUID, AgentWorkload] = {
        agent_id: AgentWorkload(
            agent_id=agent_id,
            weighted_load=0,
            active_tickets=0,
            last_assigned_at=None,
            median_resolution_seconds=None,
            resolved_sample_size=0,
        )
        for agent_id in agent_ids
    }
    if not agent_ids:
        return workloads

    load_rows = await session.exec(
        select(
            Ticket.assignee_user_id,
            func.count(Ticket.id),
            func.coalesce(func.sum(_priority_case()), 0),
        )
        .where(
            Ticket.assignee_user_id.in_(agent_ids),
            Ticket.status.in_(UNRESOLVED_STATUSES),
        )
        .group_by(Ticket.assignee_user_id)
    )
    for agent_id, active_count, weighted in load_rows.all():
        if agent_id is None or agent_id not in workloads:
            continue
        current = workloads[agent_id]
        workloads[agent_id] = AgentWorkload(
            agent_id=agent_id,
            weighted_load=int(weighted or 0),
            active_tickets=int(active_count or 0),
            last_assigned_at=current.last_assigned_at,
            median_resolution_seconds=current.median_resolution_seconds,
            resolved_sample_size=current.resolved_sample_size,
        )

    last_rows = await session.exec(
        select(Ticket.assignee_user_id, func.max(Ticket.assigned_at))
        .where(Ticket.assignee_user_id.in_(agent_ids))
        .group_by(Ticket.assignee_user_id)
    )
    for agent_id, last_assigned in last_rows.all():
        if agent_id is None or agent_id not in workloads:
            continue
        current = workloads[agent_id]
        workloads[agent_id] = AgentWorkload(
            agent_id=agent_id,
            weighted_load=current.weighted_load,
            active_tickets=current.active_tickets,
            last_assigned_at=last_assigned,
            median_resolution_seconds=current.median_resolution_seconds,
            resolved_sample_size=current.resolved_sample_size,
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_WINDOW_DAYS)
    resolved_rows = await session.exec(
        select(
            Ticket.assignee_user_id,
            Ticket.assigned_at,
            Ticket.created_at,
            Ticket.resolved_at,
        ).where(
            Ticket.assignee_user_id.in_(agent_ids),
            Ticket.resolved_at.is_not(None),
            Ticket.resolved_at >= cutoff,
        )
    )
    durations: dict[uuid.UUID, list[float]] = {agent_id: [] for agent_id in agent_ids}
    for agent_id, assigned_at, created_at, resolved_at in resolved_rows.all():
        if agent_id is None or agent_id not in durations or resolved_at is None:
            continue
        start = assigned_at or created_at
        if start is None:
            continue
        seconds = _timestamp(resolved_at, default=0.0) - _timestamp(start, default=0.0)
        if seconds >= 0:
            durations[agent_id].append(seconds)

    for agent_id, samples in durations.items():
        if len(samples) < MIN_RESOLVED_FOR_SPEED:
            continue
        samples.sort()
        middle = len(samples) // 2
        if len(samples) % 2 == 1:
            median = samples[middle]
        else:
            median = (samples[middle - 1] + samples[middle]) / 2
        current = workloads[agent_id]
        workloads[agent_id] = AgentWorkload(
            agent_id=agent_id,
            weighted_load=current.weighted_load,
            active_tickets=current.active_tickets,
            last_assigned_at=current.last_assigned_at,
            median_resolution_seconds=int(median),
            resolved_sample_size=len(samples),
        )

    return workloads


async def eligible_agents(session: AsyncSession) -> list[User]:
    """Active local users holding the AGENT role."""
    result = await session.exec(
        select(User).where(User.role == Role.AGENT, User.is_active.is_(True))
    )
    return list(result.all())


async def pick_assignee(session: AsyncSession) -> AssignmentDecision | None:
    """Choose the least-loaded eligible agent, or ``None`` when no agent is available.

    The caller must hold the assignment lock and persist the returned decision
    in the same transaction (see the ticket intake router).
    """
    agents = await eligible_agents(session)
    if not agents:
        return None

    workloads = await workload_for_agents(session, [agent.id for agent in agents])
    ranked = sorted(workloads.values(), key=lambda item: item.rank_key)

    # Walk the ranking in order. The chosen agent is re-read under a row lock
    # and re-verified so a concurrent deactivation or role change cannot race
    # the assignment; if that happens the next-best agent is tried instead of
    # giving up, so a stale snapshot never costs the customer an assignee.
    for index, winner in enumerate(ranked):
        locked = await session.get(User, winner.agent_id, with_for_update=True)
        if locked is None or locked.role != Role.AGENT or not locked.is_active:
            logger.warning(
                "Assignment: chosen agent %s became ineligible; trying the next one",
                winner.agent_id,
            )
            continue

        runner_up = ranked[index + 1] if index + 1 < len(ranked) else None
        return AssignmentDecision(
            agent_id=winner.agent_id,
            reason=_decision_reason(winner, runner_up),
            weighted_load=winner.weighted_load,
            active_tickets=winner.active_tickets,
            considered_agents=len(ranked),
            eligible_agents=len(agents),
        )

    return None


def _decision_reason(winner: AgentWorkload, runner_up: AgentWorkload | None) -> str:
    """Which step of the scoring contract separated ``winner`` from ``runner_up``."""
    if runner_up is None:
        return "ONLY_ELIGIBLE_AGENT"
    if winner.weighted_load != runner_up.weighted_load:
        return "LEAST_LOADED"
    if _timestamp(winner.last_assigned_at, default=float("-inf")) != _timestamp(
        runner_up.last_assigned_at, default=float("-inf")
    ):
        return "FAIR_ROTATION"
    if winner.median_resolution_seconds != runner_up.median_resolution_seconds:
        return "RECENT_RESOLUTION_SPEED"
    return "STABLE_ROTATION"
