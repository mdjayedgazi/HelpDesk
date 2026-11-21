from datetime import UTC, datetime, timedelta

import pytest

from app.enums.enums import Role, TicketPriority, TicketStatus


@pytest.mark.asyncio
async def test_analytics_requires_admin(client, make_user):
    customer = await make_user()
    response = await client.get(
        "/api/v1/admin/analytics", headers={"X-Test-User": customer.username}
    )
    assert response.status_code == 403

    agent = await make_user(role=Role.AGENT)
    response = await client.get(
        "/api/v1/admin/analytics", headers={"X-Test-User": agent.username}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_analytics_totals_and_breakdowns(client, make_user, make_ticket):
    admin = await make_user(role=Role.ADMIN)
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()

    await make_ticket(customer, status=TicketStatus.OPEN)
    await make_ticket(customer, status=TicketStatus.IN_PROGRESS)
    await make_ticket(customer, status=TicketStatus.WAITING_ON_CUSTOMER)
    await make_ticket(customer, status=TicketStatus.RESOLVED)
    await make_ticket(customer, status=TicketStatus.CLOSED)
    await make_ticket(
        customer,
        status=TicketStatus.IN_PROGRESS,
        priority=TicketPriority.URGENT,
        assignee=agent,
    )
    await make_ticket(customer, status=TicketStatus.OPEN, assignee=agent)

    response = await client.get(
        "/api/v1/admin/analytics", headers={"X-Test-User": admin.username}
    )
    assert response.status_code == 200
    body = response.json()

    totals = body["totals"]
    assert totals["total_tickets"] == 7
    # OPEN (2) + IN_PROGRESS (2); WAITING_ON_CUSTOMER is not counted as open.
    assert totals["open_tickets"] == 4
    assert totals["resolved_tickets"] == 1
    assert totals["closed_tickets"] == 1
    assert totals["urgent_open_tickets"] == 1
    assert totals["active_agents"] == 1

    assert body["tickets_by_status"]["OPEN"] == 2
    assert body["tickets_by_status"]["CLOSED"] == 1
    assert body["tickets_by_priority"]["URGENT"] == 1
    assert body["answered_without_resolution"] == 1

    # The window is contiguous and ends today.
    daily = body["daily"]
    assert len(daily) == body["window_days"] == 14
    assert daily[-1]["day"] == datetime.now(UTC).date().isoformat()
    assert sum(point["created"] for point in daily) == 7

    workload = body["agent_workload"]
    assert len(workload) == 1
    assert workload[0]["active_tickets"] == 2
    assert workload[0]["urgent_tickets"] == 1


@pytest.mark.asyncio
async def test_analytics_aging_and_unassigned_grace(
    client, make_user, make_ticket, session_factory
):
    """Aging and unassigned-age counters use stored timestamps, not estimates."""
    from app.models.ticket import Ticket

    admin = await make_user(role=Role.ADMIN)
    customer = await make_user()

    await make_ticket(customer, status=TicketStatus.OPEN)
    old = await make_ticket(customer, status=TicketStatus.OPEN)

    now = datetime.now(UTC)
    async with session_factory() as session:
        stale = await session.get(Ticket, old.id)
        assert stale is not None
        stale.created_at = now - timedelta(days=2)
        stale.updated_at = now - timedelta(days=9)
        session.add(stale)
        await session.commit()

    response = await client.get(
        "/api/v1/admin/analytics", headers={"X-Test-User": admin.username}
    )
    assert response.status_code == 200
    body = response.json()

    assert body["aging_over_7_days"] == 1
    assert body["unassigned_over_24h"] == 1
    assert body["totals"]["unassigned_tickets"] == 2
    assert body["totals"]["total_tickets"] == 2


@pytest.mark.asyncio
async def test_analytics_empty_database(client, make_user):
    admin = await make_user(role=Role.ADMIN)

    response = await client.get(
        "/api/v1/admin/analytics", headers={"X-Test-User": admin.username}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["totals"]["total_tickets"] == 0
    assert len(body["daily"]) == 14
    assert all(
        point["created"] == 0 and point["resolved"] == 0 for point in body["daily"]
    )
