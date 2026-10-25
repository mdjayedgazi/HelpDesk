"""Automatic ticket assignment.

These tests pin the documented scoring contract (see
``app/services/assignment.py`` and ``data.md``):

1. least weighted unresolved workload (with priority weights);
2. fairness rotation (oldest ``assigned_at`` first, never-assigned first);
3. recent resolution speed (tertiary);
4. deterministic stable rotation by agent id - no randomness.

They also cover the operational safety properties: only active AGENT accounts
are eligible, unassignable tickets stay safely in the queue with an
administrative notification, and a failure inside the assignment savepoint can
never lose the ticket.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlmodel import select

from app.api.routers import tickets as tickets_router
from app.core.database import get_db  # noqa: F401  (patched via overrides)
from app.enums.enums import NotificationType, Role, TicketPriority, TicketStatus
from app.models.notification import Notification
from app.models.ticket import Ticket
from app.models.ticketHistory import TicketHistory
from app.models.user import User
from app.services.assignment import pick_assignee

INTAKE = "/api/v1/tickets"


async def _post_ticket(client, customer, **overrides):
    payload = {
        "title": "Broken laptop",
        "description": "It will not boot.",
        "category": "TECHNICAL",
    }
    payload.update(overrides)
    return await client.post(
        INTAKE, headers={"X-Test-User": customer.username}, json=payload
    )


async def _set_assigned_at(session_factory, ticket_id, when):
    async with session_factory() as session:
        ticket = await session.get(Ticket, UUID(str(ticket_id)))
        ticket.assigned_at = when
        session.add(ticket)
        await session.commit()


async def _assignment_history(session_factory, ticket_id):
    async with session_factory() as session:
        return (
            await session.exec(
                select(TicketHistory).where(
                    TicketHistory.ticket_id == UUID(str(ticket_id)),
                    TicketHistory.event_type == "TICKET_ASSIGNED",
                )
            )
        ).all()


async def _notifications(session_factory, *, user_id, type):
    async with session_factory() as session:
        return (
            await session.exec(
                select(Notification).where(
                    Notification.recipient_user_id == user_id,
                    Notification.type == type,
                )
            )
        ).all()


@pytest.mark.asyncio
async def test_only_eligible_agent_gets_ticket(client, make_user, session_factory):
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()

    response = await _post_ticket(client, customer)
    assert response.status_code == 201
    body = response.json()
    assert body["assignee_user_id"] == str(agent.id)
    assert body["assigned_at"] is not None

    history = await _assignment_history(session_factory, body["id"])
    assert len(history) == 1
    assert history[0].new_value["assignee_user_id"] == str(agent.id)
    assert history[0].new_value["reason"] == "ONLY_ELIGIBLE_AGENT"

    notifications = await _notifications(
        session_factory, user_id=agent.id, type=NotificationType.TICKET_ASSIGNED
    )
    assert len(notifications) == 1
    assert str(body["ticket_number"]) in notifications[0].message


@pytest.mark.asyncio
async def test_least_loaded_agent_wins(client, make_user, make_ticket, session_factory):
    busy = await make_user(role=Role.AGENT)
    idle = await make_user(role=Role.AGENT)
    customer = await make_user()

    await make_ticket(customer, assignee=busy)
    await make_ticket(customer, assignee=busy)

    response = await _post_ticket(client, customer)
    assert response.status_code == 201
    assert response.json()["assignee_user_id"] == str(idle.id)

    history = await _assignment_history(session_factory, response.json()["id"])
    assert history[0].new_value["reason"] == "LEAST_LOADED"
    assert history[0].new_value["weighted_load_at_assignment"] == 0
    assert history[0].new_value["active_tickets_at_assignment"] == 0


@pytest.mark.asyncio
async def test_priority_weighting_beats_ticket_count(client, make_user, make_ticket):
    urgent_agent = await make_user(role=Role.AGENT)
    normal_agent = await make_user(role=Role.AGENT)
    customer = await make_user()

    # One urgent ticket weighs 8; three normal tickets weigh 6.
    await make_ticket(customer, assignee=urgent_agent, priority=TicketPriority.URGENT)
    for _ in range(3):
        await make_ticket(
            customer, assignee=normal_agent, priority=TicketPriority.NORMAL
        )

    response = await _post_ticket(client, customer)
    assert response.status_code == 201
    assert response.json()["assignee_user_id"] == str(normal_agent.id)


@pytest.mark.asyncio
async def test_completed_statuses_do_not_count_as_load(client, make_user, make_ticket):
    historically_busy = await make_user(role=Role.AGENT)
    fresh = await make_user(role=Role.AGENT)
    customer = await make_user()

    for status in (
        TicketStatus.RESOLVED,
        TicketStatus.RESOLVED,
        TicketStatus.CLOSED,
    ):
        await make_ticket(customer, assignee=historically_busy, status=status)

    response = await _post_ticket(client, customer)
    assert response.status_code == 201
    assert response.json()["assignee_user_id"] == str(fresh.id)


@pytest.mark.asyncio
async def test_waiting_on_customer_counts_as_load(client, make_user, make_ticket):
    waiting_agent = await make_user(role=Role.AGENT)
    free_agent = await make_user(role=Role.AGENT)
    customer = await make_user()

    await make_ticket(
        customer,
        assignee=waiting_agent,
        status=TicketStatus.WAITING_ON_CUSTOMER,
    )

    response = await _post_ticket(client, customer)
    assert response.status_code == 201
    assert response.json()["assignee_user_id"] == str(free_agent.id)


@pytest.mark.asyncio
async def test_inactive_and_non_agent_users_are_not_eligible(
    client, make_user, make_ticket, session_factory
):
    inactive = await make_user(role=Role.AGENT, is_active=False)
    await make_user(role=Role.ADMIN)
    await make_user(role=Role.OWNER)
    customer = await make_user()

    await make_ticket(customer, assignee=inactive)

    response = await _post_ticket(client, customer)
    assert response.status_code == 201
    # Admin/Owner hold no agent work; the inactive agent is skipped.
    assert response.json()["assignee_user_id"] is None

    inactive_notifications = await _notifications(
        session_factory, user_id=inactive.id, type=NotificationType.TICKET_ASSIGNED
    )
    assert inactive_notifications == []


@pytest.mark.asyncio
async def test_never_assigned_agent_sorts_first(
    client, make_user, make_ticket, session_factory
):
    previously_assigned = await make_user(role=Role.AGENT)
    never_assigned = await make_user(role=Role.AGENT)
    customer = await make_user()

    # Equal (zero) unresolved load. The old assignment has a timestamp; the
    # other agent has never been assigned, so it sorts first (NULL first).
    resolved = await make_ticket(
        customer,
        assignee=previously_assigned,
        status=TicketStatus.RESOLVED,
    )
    await _set_assigned_at(
        session_factory, resolved.id, datetime.now(UTC) - timedelta(days=1)
    )

    response = await _post_ticket(client, customer)
    assert response.status_code == 201
    assert response.json()["assignee_user_id"] == str(never_assigned.id)


@pytest.mark.asyncio
async def test_oldest_last_assignment_wins_tie(
    client, make_user, make_ticket, session_factory
):
    veteran = await make_user(role=Role.AGENT)
    recent = await make_user(role=Role.AGENT)
    customer = await make_user()

    veteran_ticket = await make_ticket(
        customer, assignee=veteran, status=TicketStatus.RESOLVED
    )
    recent_ticket = await make_ticket(
        customer, assignee=recent, status=TicketStatus.RESOLVED
    )
    now = datetime.now(UTC)
    await _set_assigned_at(session_factory, veteran_ticket.id, now - timedelta(days=30))
    await _set_assigned_at(session_factory, recent_ticket.id, now - timedelta(hours=1))

    response = await _post_ticket(client, customer)
    assert response.status_code == 201
    assert response.json()["assignee_user_id"] == str(veteran.id)

    history = await _assignment_history(session_factory, response.json()["id"])
    assert history[0].new_value["reason"] == "FAIR_ROTATION"


@pytest.mark.asyncio
async def test_stable_rotation_is_deterministic(client, make_user, session_factory):
    first = await make_user(role=Role.AGENT)
    second = await make_user(role=Role.AGENT)

    async with session_factory() as session:
        decision_one = await pick_assignee(session)
    async with session_factory() as session:
        decision_two = await pick_assignee(session)

    expected = min(first.id, second.id, key=str)
    assert decision_one is not None and decision_two is not None
    assert decision_one.reason == "STABLE_ROTATION"
    assert decision_one.agent_id == expected
    assert decision_two.agent_id == expected


@pytest.mark.asyncio
async def test_unassignable_ticket_notifies_administrators(
    client, make_user, make_ticket, session_factory
):
    admin = await make_user(role=Role.ADMIN)
    owner = await make_user(role=Role.OWNER)
    inactive = await make_user(role=Role.AGENT, is_active=False)
    customer = await make_user()

    response = await _post_ticket(client, customer)
    assert response.status_code == 201
    body = response.json()
    assert body["assignee_user_id"] is None
    assert body["assigned_at"] is None

    # The ticket is persisted and stays visible in the unassigned queue.
    async with session_factory() as session:
        stored = await session.get(Ticket, UUID(body["id"]))
    assert stored is not None and stored.assignee_user_id is None

    for recipient in (admin, owner):
        notifications = await _notifications(
            session_factory,
            user_id=recipient.id,
            type=NotificationType.TICKET_NEEDS_ASSIGNMENT,
        )
        assert len(notifications) == 1
        assert str(body["ticket_number"]) in notifications[0].message

    # The inactive agent must not have been chosen or notified.
    inactive_notifications = await _notifications(
        session_factory, user_id=inactive.id, type=NotificationType.TICKET_ASSIGNED
    )
    assert inactive_notifications == []


@pytest.mark.asyncio
async def test_assignment_failure_cannot_lose_the_ticket(
    client, make_user, session_factory, monkeypatch
):
    agent = await make_user(role=Role.AGENT)
    admin = await make_user(role=Role.ADMIN)
    customer = await make_user()

    original = tickets_router.pick_assignee

    async def boom(session):
        raise RuntimeError("simulated assignment failure")

    monkeypatch.setattr(tickets_router, "pick_assignee", boom)

    response = await _post_ticket(client, customer)
    assert response.status_code == 201
    body = response.json()
    # Never a false "assigned" answer.
    assert body["assignee_user_id"] is None
    assert body["assigned_at"] is None

    async with session_factory() as session:
        stored = await session.get(Ticket, UUID(body["id"]))
    assert stored is not None and stored.assignee_user_id is None
    assert await _assignment_history(session_factory, body["id"]) == []
    # Nothing from the rolled-back attempt leaked to the agent.
    assert (
        await _notifications(
            session_factory, user_id=agent.id, type=NotificationType.TICKET_ASSIGNED
        )
        == []
    )
    # The failure is surfaced to the administrative queue instead.
    needs_assignment = await _notifications(
        session_factory,
        user_id=admin.id,
        type=NotificationType.TICKET_NEEDS_ASSIGNMENT,
    )
    assert len(needs_assignment) == 1
    assert str(body["ticket_number"]) in needs_assignment[0].message

    # The database session recovered: the next intake assigns normally.
    monkeypatch.setattr(tickets_router, "pick_assignee", original)
    recovered = await _post_ticket(client, customer)
    assert recovered.status_code == 201
    assert recovered.json()["assignee_user_id"] == str(agent.id)


@pytest.mark.asyncio
async def test_agent_deactivated_after_ranking_falls_through_to_next(
    client, make_user, session_factory, monkeypatch
):
    """A stale eligibility snapshot must not strand the ticket.

    The ranking is computed from a snapshot; the winner is then re-read under a
    row lock. If the winner was deactivated in between, the next-ranked agent
    is chosen instead of leaving the ticket unassigned.
    """
    from app.services import assignment as assignment_service

    first = await make_user(role=Role.AGENT)
    second = await make_user(role=Role.AGENT)
    customer = await make_user()

    expected_winner = min(first.id, second.id, key=str)
    loser = second.id if expected_winner == first.id else first.id

    original_eligible = assignment_service.eligible_agents

    async def eligible_then_deactivate(session):
        agents = await original_eligible(session)
        # Deactivate the would-be winner *after* the eligibility snapshot was
        # taken, so only the locked re-read can notice it. (The unit-test
        # database shares one SQLite connection, so the change is written
        # through the same session rather than a second one; the real
        # cross-transaction race is covered by the PostgreSQL suite.)
        victim = await session.get(User, expected_winner)
        victim.is_active = False
        session.add(victim)
        await session.flush()
        return agents

    monkeypatch.setattr(assignment_service, "eligible_agents", eligible_then_deactivate)

    response = await _post_ticket(client, customer)
    assert response.status_code == 201
    assert response.json()["assignee_user_id"] == str(loser)

    history = await _assignment_history(session_factory, response.json()["id"])
    assert len(history) == 1
    assert history[0].new_value["assignee_user_id"] == str(loser)
    assert history[0].new_value["reason"] == "ONLY_ELIGIBLE_AGENT"


# A fixed assignment moment shared by every historical ticket below, so the
# fairness rotation (max ``assigned_at`` per agent) ties and the decision can
# reach the speed step. Resolutions land well inside RECENT_WINDOW_DAYS.
_HISTORY_ANCHOR = datetime.now(UTC) - timedelta(days=10)


async def _resolved_ticket(
    make_ticket, session_factory, customer, agent, *, hours: float
):
    """A ticket assigned at the anchor and resolved ``hours`` later."""
    ticket = await make_ticket(customer, assignee=agent, status=TicketStatus.RESOLVED)
    async with session_factory() as session:
        row = await session.get(Ticket, ticket.id)
        row.assigned_at = _HISTORY_ANCHOR
        row.resolved_at = _HISTORY_ANCHOR + timedelta(hours=hours)
        session.add(row)
        await session.commit()
    return ticket


@pytest.mark.asyncio
async def test_recent_resolution_speed_breaks_tie_only_with_reliable_history(
    client, make_user, make_ticket, session_factory
):
    """Speed is a tertiary tie-break and needs MIN_RESOLVED_FOR_SPEED samples."""
    from app.services.assignment import MIN_RESOLVED_FOR_SPEED

    fast = await make_user(role=Role.AGENT)
    slow = await make_user(role=Role.AGENT)
    customer = await make_user()

    # Equal zero workload. Give both agents the same "last assigned" moment so
    # the fairness rotation also ties and the decision reaches the speed step.
    for agent, hours in ((fast, 1), (slow, 48)):
        for _ in range(MIN_RESOLVED_FOR_SPEED):
            await _resolved_ticket(
                make_ticket, session_factory, customer, agent, hours=hours
            )

    response = await _post_ticket(client, customer)
    assert response.status_code == 201
    assert response.json()["assignee_user_id"] == str(fast.id)
    history = await _assignment_history(session_factory, response.json()["id"])
    assert history[0].new_value["reason"] == "RECENT_RESOLUTION_SPEED"


@pytest.mark.asyncio
async def test_insufficient_history_is_ignored_for_speed(
    make_user, make_ticket, session_factory
):
    """Below the sample threshold an agent has *no* speed measurement."""
    from app.services.assignment import MIN_RESOLVED_FOR_SPEED, workload_for_agents

    sparse = await make_user(role=Role.AGENT)
    measured = await make_user(role=Role.AGENT)
    customer = await make_user()

    for _ in range(MIN_RESOLVED_FOR_SPEED - 1):
        await _resolved_ticket(make_ticket, session_factory, customer, sparse, hours=1)
    for _ in range(MIN_RESOLVED_FOR_SPEED):
        await _resolved_ticket(
            make_ticket, session_factory, customer, measured, hours=10
        )

    async with session_factory() as session:
        workloads = await workload_for_agents(session, [sparse.id, measured.id])

    assert workloads[sparse.id].median_resolution_seconds is None
    assert workloads[sparse.id].resolved_sample_size == 0
    assert workloads[measured.id].median_resolution_seconds == 10 * 3600
    assert workloads[measured.id].resolved_sample_size == MIN_RESOLVED_FOR_SPEED


@pytest.mark.asyncio
async def test_speed_never_overrides_workload(
    client, make_user, make_ticket, session_factory
):
    """A historically fast agent must not be overloaded because of it."""
    from app.services.assignment import MIN_RESOLVED_FOR_SPEED

    fast_but_busy = await make_user(role=Role.AGENT)
    slow_but_idle = await make_user(role=Role.AGENT)
    customer = await make_user()

    for _ in range(MIN_RESOLVED_FOR_SPEED):
        await _resolved_ticket(
            make_ticket, session_factory, customer, fast_but_busy, hours=1
        )
        await _resolved_ticket(
            make_ticket, session_factory, customer, slow_but_idle, hours=72
        )
    # One open ticket is enough: workload is the primary criterion.
    await make_ticket(customer, assignee=fast_but_busy, priority=TicketPriority.LOW)

    response = await _post_ticket(client, customer)
    assert response.status_code == 201
    assert response.json()["assignee_user_id"] == str(slow_but_idle.id)
    history = await _assignment_history(session_factory, response.json()["id"])
    assert history[0].new_value["reason"] == "LEAST_LOADED"


@pytest.mark.asyncio
async def test_claim_and_admin_assignment_track_assigned_at(
    client, make_user, make_ticket, session_factory
):
    agent = await make_user(role=Role.AGENT)
    admin = await make_user(role=Role.ADMIN)
    customer = await make_user()
    ticket = await make_ticket(customer)

    claimed = await client.post(
        f"{INTAKE}/{ticket.id}/claim",
        headers={"X-Test-User": agent.username},
    )
    assert claimed.status_code == 200
    assert claimed.json()["assigned_at"] is not None

    # Admin-assisted reassignment keeps the timestamp; unassigning clears it.
    reassigned = await client.post(
        f"{INTAKE}/{ticket.id}/assign",
        headers={"X-Test-User": admin.username},
        json={"assignee_user_id": str(agent.id)},
    )
    assert reassigned.status_code == 200
    assert reassigned.json()["assigned_at"] is not None

    unassigned = await client.post(
        f"{INTAKE}/{ticket.id}/assign",
        headers={"X-Test-User": admin.username},
        json={"assignee_user_id": None},
    )
    assert unassigned.status_code == 200
    assert unassigned.json()["assigned_at"] is None

    async with session_factory() as session:
        stored = await session.get(Ticket, ticket.id)
    assert stored.assignee_user_id is None
    assert stored.assigned_at is None
