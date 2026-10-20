"""Customer feedback for a resolved ticket.

A deliberately small, single-purpose table: one optional rating (1-5) and an
optional short comment per ticket, submitted by the ticket's own customer once
the ticket is resolved. It exists so the "share feedback" notification the
customer receives on resolution has a real destination.

Rules (enforced in ``app.services.ticket_feedback`` and the router, never by the
UI):

* one row per ticket (unique constraint) - a customer can answer once;
* only the ticket's customer may submit it;
* the rating is always 1-5 (check constraint);
* the comment is optional and stored as plain text, like a comment body.

Nothing else in the application joins to this table, so it never affects ticket
workflows or visibility: it is read only by the submitting customer, the staff
working the ticket, and an administrative viewer.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Text, UniqueConstraint, func
from sqlmodel import Field, SQLModel


class TicketFeedback(SQLModel, table=True):
    __tablename__ = "ticket_feedback"
    __table_args__ = (
        # One feedback answer per ticket: the rule is the constraint, so a
        # retried submit can never create a second row.
        UniqueConstraint("ticket_id", name="uq_ticket_feedback_ticket"),
        CheckConstraint(
            "rating >= 1 AND rating <= 5",
            name="ck_ticket_feedback_rating_range",
        ),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    ticket_id: uuid.UUID = Field(foreign_key="tickets.id", nullable=False)
    # The ticket's customer. Always taken from the authenticated user, never
    # from a request body.
    customer_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    rating: int = Field(nullable=False)
    # Explicit ``Text`` matches the migration DDL exactly (see comment.py).
    comment: str | None = Field(default=None, sa_type=Text)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )
