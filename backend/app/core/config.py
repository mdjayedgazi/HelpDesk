import json
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str

    # Only the secret key is used by the backend: it signs the Clerk API calls
    # and verifies session tokens. The publishable key belongs to the frontend
    # (VITE_CLERK_PUBLISHABLE_KEY), and no webhook endpoint exists yet.
    CLERK_SECRET_KEY: str

    # The browser origin allowed by CORS and accepted as the Clerk token's
    # authorized party.
    FRONTEND_URL: str

    # Additional browser origins allowed by CORS and accepted as the Clerk
    # session token's authorized party (`azp`). Leave empty in production (only
    # FRONTEND_URL is allowed); set it in local development when the frontend
    # runs on more than one origin/port. Accepts a comma-separated list or a
    # JSON array, e.g.
    #   CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5174
    # NoDecode disables pydantic-settings' JSON-only parsing so the comma-
    # separated form below is parsed correctly.
    CORS_ORIGINS: Annotated[list[str], NoDecode] = []

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("["):
                return json.loads(text)
            return [origin.strip() for origin in text.split(",") if origin.strip()]
        return value

    @property
    def allowed_origins(self) -> list[str]:
        """FRONTEND_URL plus CORS_ORIGINS, de-duplicated, order preserved.

        Used both for CORS and for Clerk's authorized-party (`azp`) check so a
        single environment allowlist covers every permitted browser origin.
        """
        origins: list[str] = []
        for origin in [self.FRONTEND_URL, *self.CORS_ORIGINS]:
            origin = origin.strip()
            if origin and origin not in origins:
                origins.append(origin)
        return origins

    # One-time Owner bootstrap input. This is read *only* by the explicit
    # `app.commands.bootstrap_owner` command, which promotes the already-linked
    # local account whose verified Clerk primary email matches this address to
    # the permanent OWNER role. It is never consulted on the request path: the
    # application no longer elevates or demotes anyone based on this setting, so
    # removing it after the Owner has been bootstrapped never changes a stored
    # role. Empty/unset disables the bootstrap command.
    # Comparison is whitespace-insensitive and case-insensitive.
    INITIAL_ADMIN_EMAIL: str | None = None

    @property
    def initial_admin_email(self) -> str | None:
        """Normalized (trimmed, lowercased) bootstrap Owner email, or ``None``.

        ``None`` means no bootstrap identity is configured, so the bootstrap
        command refuses to run. The runtime application never calls this.
        """
        value = (self.INITIAL_ADMIN_EMAIL or "").strip().lower()
        return value or None

    # Echo every SQL statement. Useful while learning, noisy in production.
    DATABASE_ECHO: bool = False

    # Create missing tables on startup. Handy for local development, but a
    # real deployment should use migrations instead of this flag.
    AUTO_CREATE_TABLES: bool = False

    # Where uploaded attachment files are stored, and the maximum size.
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024  # 5 MiB

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
