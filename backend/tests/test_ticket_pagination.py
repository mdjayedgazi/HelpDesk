"""Pagination correctness for the ticket list endpoints.

These tests exist because the original ``GET /tickets`` contract returned a bare
list with no total, ordered only by ``created_at``. Two failure modes followed:

* Without a unique tie-breaker, rows that share a ``created_at`` could appear on
  more than one page while others were skipped entirely — empty or gapped
  intermediate pages.
* The UI had to guess "is there a next page" from ``len(items) == page_size``,
  which is wrong for a partial last page and produced an invalid trailing page.

Every test below pins the corrected contract: a ``TicketPage`` envelope whose
``total`` matches the data query, deterministic ordering, and a well-formed page
window across the whole result set.
"""

from datetime import UTC, datetime

import pytest

from app.enums.enums import Role, TicketCategory, TicketPriority, TicketStatus

TICKETS = "/api/v1/tickets"
ASSIGNED = "/api/v1/tickets/assigned"


@pytest.mark.asyncio
async def test_first_page_metadata(client, make_user, make_ticket):
    customer = await make_user()
    for index in range(5):
        await make_ticket(customer, title=f"T{index}")

    response = await client.get(TICKETS, headers={"X-Test-User": customer.username})
    assert response.status_code == 200
    body = response.json()

    assert body["page"] == 1
    assert body["page_size"] == 20
    assert body["total"] == 5
    assert body["total_pages"] == 1
    assert body["has_next"] is False
    assert body["has_previous"] is False
    assert len(body["items"]) == 5


@pytest.mark.asyncio
async def test_zero_records_is_one_empty_page(client, make_user):
    customer = await make_user()
    response = await client.get(TICKETS, headers={"X-Test-User": customer.username})
    assert response.status_code == 200
    body = response.json()

    assert body["items"] == []
    assert body["total"] == 0
    # A zero-result set still has exactly one (empty) page, never zero pages.
    assert body["total_pages"] == 1
    assert body["has_next"] is False
    assert body["has_previous"] is False


@pytest.mark.asyncio
async def test_exactly_one_page(client, make_user, make_ticket):
    customer = await make_user()
    for index in range(3):
        await make_ticket(customer, title=f"T{index}")

    body = (
        await client.get(
            TICKETS,
            headers={"X-Test-User": customer.username},
            params={"page_size": 3},
        )
    ).json()

    assert body["total"] == 3
    assert body["total_pages"] == 1
    assert body["has_next"] is False
    assert len(body["items"]) == 3


@pytest.mark.asyncio
async def test_partial_last_page_is_reachable_and_has_no_next(
    client, make_user, make_ticket
):
    customer = await make_user()
    for index in range(21):
        await make_ticket(customer, title=f"T{index}")

    last = (
        await client.get(
            TICKETS,
            headers={"X-Test-User": customer.username},
            params={"page": 2, "page_size": 20},
        )
    ).json()

    assert last["total"] == 21
    assert last["total_pages"] == 2
    assert last["page"] == 2
    assert len(last["items"]) == 1  # the partial final page
    assert last["has_next"] is False
    assert last["has_previous"] is True


@pytest.mark.asyncio
async def test_multiple_full_pages_walk_without_gaps_or_duplicates(
    client, make_user, make_ticket
):
    customer = await make_user()
    created = [await make_ticket(customer, title=f"T{i:02d}") for i in range(25)]
    expected = {str(t.id) for t in created}

    collected: list[str] = []
    page = 1
    while True:
        body = (
            await client.get(
                TICKETS,
                headers={"X-Test-User": customer.username},
                params={"page": page, "page_size": 10},
            )
        ).json()
        collected.extend(item["id"] for item in body["items"])
        if not body["has_next"]:
            break
        page += 1

    assert collected == list(dict.fromkeys(collected)), "a ticket was returned twice"
    assert set(collected) == expected, "a ticket was skipped"
    assert len(collected) == 25
    assert page == 3


@pytest.mark.asyncio
async def test_no_empty_intermediate_page_with_tied_timestamps(
    client, make_user, make_ticket, session_factory
):
    """The reported bug: tied ``created_at`` must not create gaps between pages.

    With timestamp-only ordering, PostgreSQL is free to return tied rows in a
    different physical order per OFFSET, so page N and page N+1 can overlap and
    an intermediate page can appear empty even though later rows exist. The
    unique ``id`` tie-breaker makes the order total, so every intermediate page
    is full until the genuine last page.
    """
    from sqlmodel import select

    from app.models.ticket import Ticket

    customer = await make_user()
    tied = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)
    created = []
    for index in range(15):
        created.append(await make_ticket(customer, title=f"tie-{index:02d}"))

    # Force a single shared timestamp on every ticket.
    async with session_factory() as session:
        rows = (await session.exec(select(Ticket))).all()
        for row in rows:
            row.created_at = tied
            session.add(row)
        await session.commit()

    expected = {str(t.id) for t in created}
    page_size = 5
    seen: list[str] = []
    page = 1
    while True:
        body = (
            await client.get(
                TICKETS,
                headers={"X-Test-User": customer.username},
                params={"page": page, "page_size": page_size},
            )
        ).json()
        # No intermediate page may be empty while the total says rows remain.
        assert body["items"], f"page {page} was empty but total={body['total']}"
        assert len(body["items"]) == page_size, (
            f"page {page} was short despite more pages remaining"
        )
        seen.extend(item["id"] for item in body["items"])
        if not body["has_next"]:
            break
        page += 1

    assert set(seen) == expected
    assert len(seen) == len(set(seen))
    assert len(seen) == 15


@pytest.mark.asyncio
async def test_ordering_is_newest_first_then_unique_id(client, make_user, make_ticket):
    customer = await make_user()
    first = await make_ticket(customer, title="oldest")
    second = await make_ticket(customer, title="middle")
    third = await make_ticket(customer, title="newest")

    body = (
        await client.get(TICKETS, headers={"X-Test-User": customer.username})
    ).json()
    order = [item["id"] for item in body["items"]]
    # created_at defaults differ by microseconds across the three inserts.
    assert order == [str(third.id), str(second.id), str(first.id)]


@pytest.mark.asyncio
async def test_invalid_page_and_page_size_are_rejected(client, make_user):
    customer = await make_user()
    headers = {"X-Test-User": customer.username}

    assert (
        await client.get(TICKETS, headers=headers, params={"page": 0})
    ).status_code == 422
    assert (
        await client.get(TICKETS, headers=headers, params={"page": -3})
    ).status_code == 422
    assert (
        await client.get(TICKETS, headers=headers, params={"page_size": 0})
    ).status_code == 422
    assert (
        await client.get(TICKETS, headers=headers, params={"page_size": 101})
    ).status_code == 422


@pytest.mark.asyncio
async def test_out_of_range_page_returns_empty_items_but_consistent_metadata(
    client, make_user, make_ticket
):
    """A page past the end is well-formed and never invents rows.

    The backend does not silently redirect; the frontend reconciles the page
    against this metadata. The response must still be internally consistent.
    """
    customer = await make_user()
    for index in range(3):
        await make_ticket(customer, title=f"T{index}")

    body = (
        await client.get(
            TICKETS,
            headers={"X-Test-User": customer.username},
            params={"page": 9, "page_size": 10},
        )
    ).json()

    assert body["items"] == []
    assert body["total"] == 3
    assert body["total_pages"] == 1
    assert body["page"] == 9
    # There is no page after 9, and it is not the first page.
    assert body["has_next"] is False
    assert body["has_previous"] is True


@pytest.mark.asyncio
async def test_search_combined_with_pagination(client, make_user, make_ticket):
    customer = await make_user()
    for index in range(6):
        await make_ticket(customer, title=f"billing issue {index}")
    for index in range(4):
        await make_ticket(customer, title=f"login problem {index}")

    body = (
        await client.get(
            TICKETS,
            headers={"X-Test-User": customer.username},
            params={"q": "billing", "page": 1, "page_size": 4},
        )
    ).json()

    # The search filter runs before pagination: total reflects matches only.
    assert body["total"] == 6
    assert body["total_pages"] == 2
    assert len(body["items"]) == 4
    assert all("billing" in item["title"].lower() for item in body["items"])


@pytest.mark.asyncio
async def test_status_filter_combined_with_pagination(client, make_user, make_ticket):
    customer = await make_user()
    for index in range(7):
        await make_ticket(customer, title=f"open {index}", status=TicketStatus.OPEN)
    for index in range(3):
        await make_ticket(customer, title=f"closed {index}", status=TicketStatus.CLOSED)

    body = (
        await client.get(
            TICKETS,
            headers={"X-Test-User": customer.username},
            params={"status": "OPEN", "page": 2, "page_size": 4},
        )
    ).json()

    assert body["total"] == 7  # OPEN only
    assert body["total_pages"] == 2
    assert len(body["items"]) == 3  # 7 - 4 on page 1
    assert all(item["status"] == "OPEN" for item in body["items"])


@pytest.mark.asyncio
async def test_priority_filter_combined_with_pagination(client, make_user, make_ticket):
    customer = await make_user()
    for index in range(5):
        await make_ticket(
            customer, title=f"urgent {index}", priority=TicketPriority.URGENT
        )
    for index in range(5):
        await make_ticket(customer, title=f"low {index}", priority=TicketPriority.LOW)

    body = (
        await client.get(
            TICKETS,
            headers={"X-Test-User": customer.username},
            params={"priority": "URGENT", "page_size": 3},
        )
    ).json()

    assert body["total"] == 5
    assert body["total_pages"] == 2
    assert all(item["priority"] == "URGENT" for item in body["items"])


@pytest.mark.asyncio
async def test_category_filter_combined_with_pagination(client, make_user, make_ticket):
    customer = await make_user()
    for index in range(4):
        await make_ticket(
            customer, title=f"bill {index}", category=TicketCategory.BILLING
        )
    await make_ticket(customer, title="other", category=TicketCategory.OTHER)

    body = (
        await client.get(
            TICKETS,
            headers={"X-Test-User": customer.username},
            params={"category": "BILLING", "page_size": 2, "page": 2},
        )
    ).json()

    assert body["total"] == 4
    assert body["total_pages"] == 2
    assert len(body["items"]) == 2
    assert all(item["category"] == "BILLING" for item in body["items"])


@pytest.mark.asyncio
async def test_unassigned_filter_is_server_side_and_paginated(
    client, make_user, make_ticket
):
    """``unassigned=true`` must filter in SQL, not after the page window."""
    admin = await make_user(role=Role.ADMIN)
    customer = await make_user()
    for index in range(6):
        await make_ticket(customer, title=f"free {index}")  # unassigned
    for index in range(6):
        await make_ticket(customer, title=f"owned {index}", assignee=admin)

    body = (
        await client.get(
            TICKETS,
            headers={"X-Test-User": admin.username},
            params={"unassigned": "true", "page": 1, "page_size": 4},
        )
    ).json()

    # 6 unassigned of 12 total; the page is full and every row is unassigned.
    assert body["total"] == 6
    assert body["total_pages"] == 2
    assert len(body["items"]) == 4
    assert all(item["assignee_user_id"] is None for item in body["items"])

    last = (
        await client.get(
            TICKETS,
            headers={"X-Test-User": admin.username},
            params={"unassigned": "true", "page": 2, "page_size": 4},
        )
    ).json()
    assert len(last["items"]) == 2
    assert last["has_next"] is False


@pytest.mark.asyncio
async def test_assigned_filter_combined_with_pagination(client, make_user, make_ticket):
    admin = await make_user(role=Role.ADMIN)
    other = await make_user(role=Role.AGENT)
    customer = await make_user()
    for index in range(5):
        await make_ticket(customer, title=f"admin {index}", assignee=admin)
    for index in range(3):
        await make_ticket(customer, title=f"other {index}", assignee=other)

    body = (
        await client.get(
            TICKETS,
            headers={"X-Test-User": admin.username},
            params={"assignee_user_id": str(admin.id), "page_size": 2},
        )
    ).json()

    assert body["total"] == 5
    assert body["total_pages"] == 3
    assert all(item["assignee_user_id"] == str(admin.id) for item in body["items"])


@pytest.mark.asyncio
async def test_role_visibility_combined_with_pagination(client, make_user, make_ticket):
    """A customer's total counts only their own tickets, never the global set."""
    alice = await make_user()
    bob = await make_user()
    for index in range(6):
        await make_ticket(alice, title=f"alice {index}")
    for index in range(9):
        await make_ticket(bob, title=f"bob {index}")

    alice_body = (
        await client.get(
            TICKETS,
            headers={"X-Test-User": alice.username},
            params={"page_size": 4},
        )
    ).json()
    assert alice_body["total"] == 6
    assert alice_body["total_pages"] == 2
    assert all(
        item["created_by_user_id"] == str(alice.id) for item in alice_body["items"]
    )


@pytest.mark.asyncio
async def test_agent_visibility_counts_assigned_and_unassigned(
    client, make_user, make_ticket
):
    agent = await make_user(role=Role.AGENT)
    other_agent = await make_user(role=Role.AGENT)
    customer = await make_user()

    for index in range(3):
        await make_ticket(customer, title=f"mine {index}", assignee=agent)
    for index in range(2):
        await make_ticket(customer, title=f"free {index}")
    for index in range(4):
        await make_ticket(customer, title=f"theirs {index}", assignee=other_agent)

    body = (
        await client.get(
            TICKETS,
            headers={"X-Test-User": agent.username},
            params={"page_size": 20},
        )
    ).json()

    # Agent sees own assigned (3) + unassigned (2), never another agent's (4).
    assert body["total"] == 5
    ids = {item["id"] for item in body["items"]}
    assert len(ids) == 5


@pytest.mark.asyncio
async def test_assigned_endpoint_envelope_and_deterministic_order(
    client, make_user, make_ticket
):
    agent = await make_user(role=Role.AGENT)
    customer = await make_user()
    made = []
    for index in range(5):
        made.append(await make_ticket(customer, title=f"q{index}", assignee=agent))

    body = (
        await client.get(
            ASSIGNED,
            headers={"X-Test-User": agent.username},
            params={"page": 1, "page_size": 2},
        )
    ).json()

    assert body["total"] == 5
    assert body["total_pages"] == 3
    assert body["has_next"] is True
    assert len(body["items"]) == 2
    # Newest first.
    assert body["items"][0]["id"] == str(made[-1].id)


@pytest.mark.asyncio
async def test_different_page_sizes_cover_the_same_set(client, make_user, make_ticket):
    customer = await make_user()
    for index in range(10):
        await make_ticket(customer, title=f"T{index}")

    headers = {"X-Test-User": customer.username}

    for page_size in (3, 4, 10):
        seen: list[str] = []
        page = 1
        while True:
            body = (
                await client.get(
                    TICKETS,
                    headers=headers,
                    params={"page": page, "page_size": page_size},
                )
            ).json()
            seen.extend(item["id"] for item in body["items"])
            if not body["has_next"]:
                break
            page += 1
        assert len(seen) == 10
        assert len(set(seen)) == 10


@pytest.mark.asyncio
async def test_created_at_ties_use_id_tiebreaker_across_pages(
    client, make_user, make_ticket, session_factory
):
    from sqlmodel import select

    from app.models.ticket import Ticket

    customer = await make_user()
    for index in range(9):
        await make_ticket(customer, title=f"tie-{index}")

    tied = datetime(2026, 11, 5, 9, 0, 0, tzinfo=UTC)
    async with session_factory() as session:
        for row in (await session.exec(select(Ticket))).all():
            row.created_at = tied
            session.add(row)
        await session.commit()

    headers = {"X-Test-User": customer.username}
    page1 = (
        await client.get(TICKETS, headers=headers, params={"page": 1, "page_size": 4})
    ).json()
    page2 = (
        await client.get(TICKETS, headers=headers, params={"page": 2, "page_size": 4})
    ).json()

    ids1 = [item["id"] for item in page1["items"]]
    ids2 = [item["id"] for item in page2["items"]]
    # No overlap even though every created_at is identical.
    assert set(ids1).isdisjoint(ids2)
    # Deterministic: the same page request returns the same rows.
    repeat = (
        await client.get(TICKETS, headers=headers, params={"page": 1, "page_size": 4})
    ).json()
    assert [item["id"] for item in repeat["items"]] == ids1


@pytest.mark.asyncio
async def test_total_matches_count_query_not_page_length(
    client, make_user, make_ticket
):
    customer = await make_user()
    for index in range(37):
        await make_ticket(customer, title=f"T{index}")

    body = (
        await client.get(
            TICKETS,
            headers={"X-Test-User": customer.username},
            params={"page": 1, "page_size": 20},
        )
    ).json()

    # The page has 20 rows, but the total is 37 — the UI must use the total,
    # not the page length, to decide whether a next page exists.
    assert len(body["items"]) == 20
    assert body["total"] == 37
    assert body["total_pages"] == 2
    assert body["has_next"] is True


@pytest.mark.asyncio
async def test_page_env_reports_effective_page_size(client, make_user, make_ticket):
    customer = await make_user()
    for index in range(3):
        await make_ticket(customer, title=f"T{index}")

    body = (
        await client.get(
            TICKETS,
            headers={"X-Test-User": customer.username},
            params={"page_size": 2},
        )
    ).json()

    assert body["page_size"] == 2
    assert body["total_pages"] == 2


def test_paginated_query_orders_by_created_at_then_unique_id():
    """Structural guard for the fix itself.

    A timestamp-only order is not a total order, so LIMIT/OFFSET is not stable
    when rows tie. This asserts the compiled SQL orders by ``created_at DESC``
    followed by the unique primary key, independent of PostgreSQL's planner or
    table statistics (which can make an execution-only test pass by luck).
    """
    from sqlalchemy.dialects import postgresql

    from app.services.tickets import paginate_tickets

    statement = paginate_tickets([], limit=20, offset=0)
    sql = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    ).upper()

    order_by = sql.split("ORDER BY", 1)[1]
    assert "CREATED_AT DESC" in order_by
    assert "ID DESC" in order_by
    # The unique tie-breaker must come after the requested sort key.
    assert order_by.index("CREATED_AT DESC") < order_by.index("ID DESC")
    assert "LIMIT 20" in sql
    assert "OFFSET 0" in sql
