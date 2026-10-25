import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, func, text
from sqlmodel import Field, Relationship, SQLModel

from app.enums.enums import AttachmentScanStatus
from app.models.ticket import Ticket
from app.models.user import User


class Attachment(SQLModel, table=True):
    __tablename__ = "attachments"
    __table_args__ = (
        CheckConstraint("size_bytes >= 0", name="ck_attachments_size_nonnegative"),
    )

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    ticket_id: uuid.UUID = Field(foreign_key="tickets.id", index=True, nullable=False)
    uploaded_by_user_id: uuid.UUID = Field(foreign_key="users.id", nullable=False)
    original_filename: str = Field(max_length=255, nullable=False)
    storage_key: str = Field(max_length=500, unique=True, nullable=False)
    content_type: str = Field(max_length=120, nullable=False)
    size_bytes: int = Field(ge=0, nullable=False)
    scan_status: AttachmentScanStatus = Field(
        default=AttachmentScanStatus.PENDING,
        nullable=False,
        sa_column_kwargs={"server_default": text("'PENDING'")},
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        sa_type=DateTime(timezone=True),
        nullable=False,
        sa_column_kwargs={"server_default": func.now()},
    )

    ticket: Ticket = Relationship(back_populates="attachments")
    uploaded_by: User = Relationship(back_populates="attachments")
