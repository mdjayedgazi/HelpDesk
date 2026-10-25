import ipaddress
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

    # Malware scanning. Uploads are rejected (fail closed) unless a ClamAV
    # daemon is explicitly configured. Magic-byte checks are not malware
    # scanning and are never treated as a clean result.
    MALWARE_SCAN_ENABLED: bool = False
    CLAMAV_HOST: str | None = None
    CLAMAV_PORT: int = 3310
    CLAMAV_TIMEOUT_SECONDS: float = 10.0

    # Distributed rate limiting. Disabled by default because enabling it
    # without a shared Redis instance would give a false sense of protection.
    # When enabled, an unavailable Redis fails closed with 503 rather than
    # silently allowing unlimited traffic.
    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_REDIS_URL: str | None = None
    RATE_LIMIT_REDIS_TIMEOUT_SECONDS: float = 0.5
    # Only these direct peers may supply X-Forwarded-For. An empty list means
    # the header is ignored and the TCP peer address is used.
    RATE_LIMIT_TRUSTED_PROXIES: Annotated[list[str], NoDecode] = []
    RATE_LIMIT_WINDOW_SECONDS: int = 60
    RATE_LIMIT_ACCOUNT_REQUEST_WINDOW_SECONDS: int = 3600
    RATE_LIMIT_TICKET_CREATE: int = 10
    RATE_LIMIT_COMMENT_CREATE: int = 30
    RATE_LIMIT_ATTACHMENT_UPLOAD: int = 20
    RATE_LIMIT_FEEDBACK_CREATE: int = 10
    RATE_LIMIT_ACCOUNT_REQUEST_CREATE: int = 10
    RATE_LIMIT_ACCOUNT_REQUEST_COMMENT: int = 30
    RATE_LIMIT_STAFF_MESSAGE_CREATE: int = 60
    RATE_LIMIT_INTERNAL_MESSAGE_CREATE: int = 20

    @field_validator("RATE_LIMIT_TRUSTED_PROXIES", mode="before")
    @classmethod
    def _parse_trusted_proxies(cls, value: object) -> object:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            values = (
                json.loads(text)
                if text.startswith("[")
                else [item.strip() for item in text.split(",") if item.strip()]
            )
        elif isinstance(value, (list, tuple)):
            values = list(value)
        else:
            return value

        parsed: list[str] = []
        for item in values:
            if not isinstance(item, str):
                raise TypeError("RATE_LIMIT_TRUSTED_PROXIES entries must be strings")
            network = ipaddress.ip_network(item.strip(), strict=False)
            parsed.append(str(network))
        return parsed

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
