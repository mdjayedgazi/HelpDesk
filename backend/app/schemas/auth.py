
from pydantic import ConfigDict, EmailStr, model_validator
from sqlmodel import Field, SQLModel


class ForgotPasswordRequest(SQLModel):
    """Request a password-reset link by email."""

    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class ResetPasswordRequest(SQLModel):
    """Reset a forgotten password using a reset token."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=4096)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_new_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_passwords(self):
        if self.new_password != self.confirm_new_password:
            raise ValueError("Passwords do not match")

        return self


class ChangePasswordRequest(SQLModel):
    """Change a password when the user knows the current password."""

    model_config = ConfigDict(extra="forbid")

    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)
    confirm_new_password: str = Field(min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_passwords(self):
        if self.new_password != self.confirm_new_password:
            raise ValueError("Passwords do not match")

        if self.current_password == self.new_password:
            raise ValueError("New password must differ from current password")

        return self


class PasswordMessage(SQLModel):
    message: str
