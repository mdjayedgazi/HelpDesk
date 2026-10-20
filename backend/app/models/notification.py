import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, func, text
from sqlmodel import Field, Relationship, SQLModel

from app.enums.enums import NotificationType
from app.models.ticket import Ticket
from app.models.user import User


class Notification(SQLModel, table=True):
    __tablename__ = "notifications"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    recipient_user_id: uuid.UUID = Field(foreign_key="users.id", index=True, nullable=False)
    related_ticket_id: uuid.UUID | None = Field(default=None, foreign_key="tickets.id")
    # Optional deep link for notifications about a private staff conversation.
    # Customers never receive these notifications, and the conversation itself
    # enforces its own authorization.
    related_conversation_id: uuid.UUID | None = Field(
        default=None, foreign_key="staff_conversations.id"
    )
    # Optional deep link for an Owner-composed internal message (Owner Inbox).
    # The message payload is never copied here; the recipient's own access rules
    # still decide whether they can open it.
    related_internal_message_id: uuid.UUID | None = Field(
        default=None, foreign_key="internal_messages.id"
    )
    # Optional deep link for an account-management request (admin escalation),
    # so the reviewer opens the request itself rather than only its ticket.
    related_account_request_id: uuid.UUID | None = Field(
        default=None, foreign_key="account_management_requests.id"
    )
    type: NotificationType = Field(max_length=40, nullable=False)
    title: str = Field(max_length=180, nullable=False)
    message: str = Field(max_length=500, nullable=False)
    is_read: bool = Field(
        default=False,
        nullable=False,
        sa_column_kwargs={"server_default": text("false")},
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )

    recipient: User = Relationship(back_populates="notifications")
    related_ticket: Ticket | None = Relationship(back_populates="notifications")