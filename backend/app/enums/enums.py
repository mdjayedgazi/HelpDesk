from enum import Enum
class Role(str, Enum):
    CUSTOMER = "CUSTOMER"
    ADMIN = "ADMIN"
    AGENT = "AGENT"


class TicketStatus(str, Enum):
    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    WAITING_ON_CUSTOMER = "WAITING_ON_CUSTOMER"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"


class TicketPriority(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    URGENT = "URGENT"


class NotificationType(str, Enum):
    TICKET_ASSIGNED = "TICKET_ASSIGNED"
    NEW_COMMENT = "NEW_COMMENT"
    STATUS_CHANGED = "STATUS_CHANGED"
    PRIORITY_CHANGED = "PRIORITY_CHANGED"