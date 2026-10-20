import pytest

from app.enums.enums import Role


@pytest.mark.asyncio
async def test_notifications_are_per_user(
    client, make_user, make_ticket, session_factory
):
    from app.services.notifications import create_notification
    from app.enums.enums import NotificationType

    owner = await make_user()
    other = await make_user()
    ticket = await make_ticket(owner)

    async with session_factory() as session:
        create_notification(
            session,
            recipient_user_id=owner.id,
            related_ticket_id=ticket.id,
            type=NotificationType.STATUS_CHANGED,
            title="Owner notice",
            message="Only the owner should see this.",
        )
        await session.commit()

    response = await client.get(
        "/api/v1/notifications", headers={"X-Test-User": owner.username}
    )
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = await client.get(
        "/api/v1/notifications", headers={"X-Test-User": other.username}
    )
    assert response.json() == []


@pytest.mark.asyncio
async def test_mark_notification_read(client, make_user, make_ticket, session_factory):
    from app.enums.enums import NotificationType
    from app.services.notifications import create_notification

    owner = await make_user()
    other = await make_user()
    ticket = await make_ticket(owner)

    async with session_factory() as session:
        notification = create_notification(
            session,
            recipient_user_id=owner.id,
            related_ticket_id=ticket.id,
            type=NotificationType.STATUS_CHANGED,
            title="Notice",
            message="Read me.",
        )
        await session.commit()
        await session.refresh(notification)
        notification_id = notification.id

    # Another user cannot touch it.
    forbidden = await client.patch(
        f"/api/v1/notifications/{notification_id}",
        headers={"X-Test-User": other.username},
        json={"is_read": True},
    )
    assert forbidden.status_code == 404

    ok = await client.patch(
        f"/api/v1/notifications/{notification_id}",
        headers={"X-Test-User": owner.username},
        json={"is_read": True},
    )
    assert ok.status_code == 200
    assert ok.json()["is_read"] is True


@pytest.mark.asyncio
async def test_notification_update_rejects_unknown_fields(client, make_user):
    user = await make_user()
    response = await client.patch(
        "/api/v1/notifications/00000000-0000-0000-0000-000000000000",
        headers={"X-Test-User": user.username},
        json={"is_read": True, "recipient_user_id": str(user.id)},
    )
    # Unknown fields are rejected before the notification is even looked up.
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_agent_role_is_required_for_agent_endpoints(client, make_user):
    customer = await make_user(role=Role.CUSTOMER)
    response = await client.get(
        "/api/v1/tickets/assigned",
        headers={"X-Test-User": customer.username},
    )
    assert response.status_code == 403
