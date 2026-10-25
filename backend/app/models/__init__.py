"""Model package.

Importing this package registers every SQLModel table on
``SQLModel.metadata`` so that ``create_all()`` and the mappers see them.
The import order matters: dependent models are imported after the models
they reference.
"""

from app.models.account_request import (
    AccountManagementRequest,
    AccountRequestComment,
    AccountRequestEvent,
)
from app.models.attachment import Attachment
from app.models.comment import Comment
from app.models.internal_message import InternalMessage, InternalMessageRecipient
from app.models.notification import Notification
from app.models.staff_message import StaffConversation, StaffMessage
from app.models.ticket import Ticket
from app.models.ticket_feedback import TicketFeedback
from app.models.ticketHistory import TicketHistory
from app.models.user import User

__all__ = [
    "AccountManagementRequest",
    "AccountRequestComment",
    "AccountRequestEvent",
    "Attachment",
    "Comment",
    "InternalMessage",
    "InternalMessageRecipient",
    "Notification",
    "StaffConversation",
    "StaffMessage",
    "Ticket",
    "TicketFeedback",
    "TicketHistory",
    "User",
]
