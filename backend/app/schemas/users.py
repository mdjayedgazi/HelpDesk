import uuid
from datetime import datetime
from typing import Annotated

from email_validator import EmailSyntaxError, validate_email
from pydantic import AfterValidator, BeforeValidator, ConfigDict
from sqlmodel import Field, SQLModel

from app.enums.enums import AssignableRole, Role


def _stripped(value: object) -> object:
    """Trim before length validation so whitespace-only names are rejected."""
    if isinstance(value, str):
        return value.strip()
    return value


TrimmedText = Annotated[str, BeforeValidator(_stripped)]


def _valid_email(value: str) -> str:
    """Validate an email address, permitting reserved/special-use domains.

    ``pydantic.EmailStr`` rejects the reserved IANA special-use domains
    (``.test``, ``.invalid``, ``.localhost`` and ``.example``) outright. Those
    addresses are syntactically valid and are exactly what QA/staging fixtures
    and documentation use, so an application that stores them must be able to
    echo them back. ``test_environment=True`` keeps the full syntax checks while
    allowing those domains; deliverability is never checked (the app does not
    send mail).
    """
    if not isinstance(value, str):  # pragma: no cover - defensive
        raise TypeError("Email address must be a string")
    try:
        validate_email(value, check_deliverability=False, test_environment=True)
    except EmailSyntaxError as exc:
        raise ValueError(str(exc)) from None
    return value


# An email address that validates syntactically but accepts reserved domains.
# Used for *input* schemas only. Response schemas use ``str`` so that data
# already stored in the database is never re-validated at serialization time
# (which previously turned a stored ``.test`` address into an HTTP 500).
EmailAddress = Annotated[str, AfterValidator(_valid_email)]


class UserUpdate(SQLModel):
    """Fields a user may change on their own profile (GET/PATCH /users/me).

    ``email`` is accepted only so a client that submits the whole profile can
    be rejected with a clear 422 instead of silently changing identity. The
    router refuses any value that differs from the stored address; Clerk remains
    the authoritative source of the verified email.
    """

    model_config = ConfigDict(extra="forbid")

    full_name: TrimmedText | None = Field(default=None, min_length=2, max_length=120)
    username: TrimmedText | None = Field(default=None, min_length=2, max_length=90)
    email: EmailAddress | None = None


class UserAdminUpdate(SQLModel):
    """Fields the Owner may change on another user's account.

    ``role`` is an ``AssignableRole``, which deliberately excludes OWNER: the
    generic update endpoint can never create or transfer ownership.
    """

    model_config = ConfigDict(extra="forbid")

    full_name: TrimmedText | None = Field(default=None, min_length=2, max_length=120)
    username: TrimmedText | None = Field(default=None, min_length=2, max_length=90)
    email: EmailAddress | None = None
    role: AssignableRole | None = None
    is_active: bool | None = None


class UserRoleUpdate(SQLModel):
    """The role-change request body. Owner-only endpoint; OWNER is not allowed."""

    model_config = ConfigDict(extra="forbid")

    role: AssignableRole


class UserStatusUpdate(SQLModel):
    model_config = ConfigDict(extra="forbid")

    is_active: bool


class UserRead(SQLModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    full_name: str
    username: str
    email: str
    role: Role
    is_active: bool
    image_url: str | None = None
    created_at: datetime
    updated_at: datetime
