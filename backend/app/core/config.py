import ipaddress
import json
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# Values that must never be accepted in a production deployment. These are
# matched case-insensitively against configuration values; the error messages
# name the variable only, never the supplied value.
_PLACEHOLDER_MARKERS = (
    "replace",
    "change-me",
    "changeme",
    "your-",
    "your_",
    "example",
    "dummy",
    "placeholder",
    "<",
    ">",
)
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1", "host.docker.internal"}


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.strip().lower()
    return not lowered or any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


class Settings(BaseSettings):
    DATABASE_URL: str

    # Only the secret key is used by the backend: it signs the Clerk API calls
    # and verifies session tokens. The publishable key belongs to the frontend
    # (VITE_CLERK_PUBLISHABLE_KEY), and no webhook endpoint exists yet.
    CLERK_SECRET_KEY: str

    # The browser origin allowed by CORS and accepted as the Clerk token's
    # authorized party.
    FRONTEND_URL: str

    # ``development`` and ``test`` keep the local conveniences. ``production``
    # turns on fail-closed configuration checks below and disables the OpenAPI
    # documentation routes.
    ENVIRONMENT: Literal["development", "test", "production"] = "development"

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
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def docs_enabled(self) -> bool:
        """Swagger/OpenAPI is a development aid, not a production surface."""
        return not self.is_production

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

    # PostgreSQL connection pool settings. These are ignored for
    # the in-memory SQLite test database, whose pool is managed by SQLite.
    DB_POOL_SIZE: int = 5
    DB_MAX_OVERFLOW: int = 10
    DB_POOL_TIMEOUT_SECONDS: float = 30.0
    DB_POOL_RECYCLE_SECONDS: int = 1800
    DB_CONNECT_TIMEOUT_SECONDS: int = 10

    # Where uploaded attachment files are stored, and the maximum size.
    # UPLOAD_DIR must be on a persistent volume in production.
    UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024  # 5 MiB
    # Multipart framing adds a small amount above the file itself. The request
    # body middleware rejects anything larger before FastAPI parses/spools it.
    MAX_MULTIPART_OVERHEAD_BYTES: int = 1024 * 1024  # 1 MiB
    MAX_JSON_BODY_BYTES: int = 1_000_000  # 1 MB
    # Per-ticket upload quotas. The rate limiter also bounds upload velocity.
    MAX_ATTACHMENTS_PER_TICKET: int = 20
    MAX_TICKET_ATTACHMENT_BYTES: int = 50 * 1024 * 1024  # 50 MiB

    @property
    def max_upload_request_bytes(self) -> int:
        return self.MAX_UPLOAD_BYTES + self.MAX_MULTIPART_OVERHEAD_BYTES

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
    # silently allowing unlimited traffic. Production refuses to start unless
    # this is enabled and a shared Redis URL is configured.
    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_REDIS_URL: str | None = None
    RATE_LIMIT_REDIS_TIMEOUT_SECONDS: float = 0.5
    # Only these direct peers may supply X-Forwarded-For. An empty list means
    # the header is ignored and the TCP peer address is used. Behind Railway's
    # edge, set this explicitly (see docs/DEPLOYMENT.md) because the edge is the
    # only network path to the service.
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
    RATE_LIMIT_NOTIFICATION_POLL: int = 120

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

    # Security headers. HSTS is opt-in and must only be enabled after HTTPS is
    # verified end-to-end; enabling it on an HTTP-only origin would lock users
    # out of the site.
    HSTS_ENABLED: bool = False
    HSTS_MAX_AGE_SECONDS: int = 31_536_000

    # Logging: JSON is recommended in production. ``None`` means "JSON when
    # ENVIRONMENT=production, human-readable otherwise".
    LOG_LEVEL: str = "INFO"
    LOG_JSON: bool | None = None

    @property
    def log_json(self) -> bool:
        return self.is_production if self.LOG_JSON is None else self.LOG_JSON

    def model_post_init(self, __context: object) -> None:
        """Run fail-closed production checks after Pydantic parsing.

        A plain ``RuntimeError`` is used instead of a validation error so the
        traceback never echoes the whole settings input (which may contain
        credentials) into logs.
        """
        self._validate_production_configuration()

    def _validate_production_configuration(self) -> None:
        """Fail closed before a production process can serve traffic.

        Development and test keep the convenient local defaults. Production is
        deliberately strict: no placeholder credentials, no localhost origins,
        no disabled abuse controls, and no relative upload path.
        """
        if not self.is_production:
            return

        problems: list[str] = []

        def add(problem: str) -> None:
            problems.append(problem)

        frontend = urlsplit(self.FRONTEND_URL)
        if (
            frontend.scheme != "https"
            or not frontend.netloc
            or (frontend.hostname or "").lower() in _LOCAL_HOSTS
            or frontend.path not in ("", "/")
            or frontend.query
            or frontend.fragment
        ):
            add("FRONTEND_URL must be an exact https:// origin (no path/query)")
        if _looks_like_placeholder(self.FRONTEND_URL):
            add("FRONTEND_URL must not contain a placeholder value")

        for origin in self.CORS_ORIGINS:
            parsed = urlsplit(origin)
            if (
                parsed.scheme != "https"
                or not parsed.netloc
                or (parsed.hostname or "").lower() in _LOCAL_HOSTS
                or parsed.path not in ("", "/")
                or parsed.query
                or parsed.fragment
            ):
                add("CORS_ORIGINS entries must be exact https:// origins")
                break
            if _looks_like_placeholder(origin):
                add("CORS_ORIGINS entries must not contain placeholder values")
                break
        if "*" in self.allowed_origins:
            add("Wildcard CORS origins are not allowed in production")

        if not self.CLERK_SECRET_KEY.startswith("sk_live_"):
            add("CLERK_SECRET_KEY must be a Clerk production secret (sk_live_...)")
        if _looks_like_placeholder(self.CLERK_SECRET_KEY):
            add("CLERK_SECRET_KEY contains a placeholder value")

        db = urlsplit(self.DATABASE_URL)
        if db.scheme not in {
            "postgresql",
            "postgresql+psycopg",
            "postgres",
        }:
            add("DATABASE_URL must use PostgreSQL with the psycopg driver")
        if not db.hostname or db.hostname.lower() in _LOCAL_HOSTS:
            add("DATABASE_URL must not point at localhost in production")
        if _looks_like_placeholder(self.DATABASE_URL):
            add("DATABASE_URL contains a placeholder value")

        if not self.RATE_LIMIT_ENABLED:
            add("RATE_LIMIT_ENABLED must be true in production")
        redis = urlsplit(self.RATE_LIMIT_REDIS_URL or "")
        if redis.scheme not in {"redis", "rediss"} or not redis.hostname:
            add("RATE_LIMIT_REDIS_URL must be a redis:// or rediss:// URL")
        elif redis.hostname.lower() in _LOCAL_HOSTS:
            add("RATE_LIMIT_REDIS_URL must not point at localhost in production")
        if not self.RATE_LIMIT_TRUSTED_PROXIES:
            add(
                "RATE_LIMIT_TRUSTED_PROXIES must explicitly describe the "
                "reverse proxy/edge that supplies X-Forwarded-For"
            )
        if self.RATE_LIMIT_REDIS_TIMEOUT_SECONDS <= 0:
            add("RATE_LIMIT_REDIS_TIMEOUT_SECONDS must be positive")
        if self.RATE_LIMIT_WINDOW_SECONDS <= 0:
            add("RATE_LIMIT_WINDOW_SECONDS must be positive")
        if self.RATE_LIMIT_ACCOUNT_REQUEST_WINDOW_SECONDS <= 0:
            add("RATE_LIMIT_ACCOUNT_REQUEST_WINDOW_SECONDS must be positive")
        for field_name in (
            "RATE_LIMIT_TICKET_CREATE",
            "RATE_LIMIT_COMMENT_CREATE",
            "RATE_LIMIT_ATTACHMENT_UPLOAD",
            "RATE_LIMIT_FEEDBACK_CREATE",
            "RATE_LIMIT_ACCOUNT_REQUEST_CREATE",
            "RATE_LIMIT_ACCOUNT_REQUEST_COMMENT",
            "RATE_LIMIT_STAFF_MESSAGE_CREATE",
            "RATE_LIMIT_INTERNAL_MESSAGE_CREATE",
            "RATE_LIMIT_NOTIFICATION_POLL",
        ):
            if getattr(self, field_name) <= 0:
                add(f"{field_name} must be positive")

        if not self.MALWARE_SCAN_ENABLED:
            add("MALWARE_SCAN_ENABLED must be true in production")
        if not self.CLAMAV_HOST or self.CLAMAV_HOST.strip().lower() in _LOCAL_HOSTS:
            add("CLAMAV_HOST must point at a reachable ClamAV service")
        if not 1 <= self.CLAMAV_PORT <= 65_535:
            add("CLAMAV_PORT must be a valid TCP port")
        if self.CLAMAV_TIMEOUT_SECONDS <= 0:
            add("CLAMAV_TIMEOUT_SECONDS must be positive")

        if self.HSTS_MAX_AGE_SECONDS < 0:
            add("HSTS_MAX_AGE_SECONDS must be zero or positive")
        if self.LOG_LEVEL.upper() not in {
            "CRITICAL",
            "ERROR",
            "WARNING",
            "WARN",
            "INFO",
            "DEBUG",
            "NOTSET",
        }:
            add("LOG_LEVEL must be a standard logging level")

        upload_dir = self.UPLOAD_DIR.strip()
        if not upload_dir.startswith("/"):
            add("UPLOAD_DIR must be an absolute path on a persistent volume")
        elif upload_dir == "/" or upload_dir.startswith(("/tmp", "/var/tmp")):
            add("UPLOAD_DIR must be a durable path, not / or a temp directory")

        if self.AUTO_CREATE_TABLES:
            add("AUTO_CREATE_TABLES must be false in production (use Alembic)")
        if self.DATABASE_ECHO:
            add("DATABASE_ECHO must be false in production")

        if self.DB_POOL_SIZE <= 0:
            add("DB_POOL_SIZE must be positive")
        if self.DB_MAX_OVERFLOW < 0:
            add("DB_MAX_OVERFLOW must be zero or positive")
        if self.DB_POOL_TIMEOUT_SECONDS <= 0:
            add("DB_POOL_TIMEOUT_SECONDS must be positive")
        if self.DB_POOL_RECYCLE_SECONDS < 0:
            add("DB_POOL_RECYCLE_SECONDS must be zero or positive")
        if self.DB_CONNECT_TIMEOUT_SECONDS <= 0:
            add("DB_CONNECT_TIMEOUT_SECONDS must be positive")

        if self.MAX_UPLOAD_BYTES <= 0:
            add("MAX_UPLOAD_BYTES must be positive")
        if self.MAX_JSON_BODY_BYTES <= 0:
            add("MAX_JSON_BODY_BYTES must be positive")
        if self.MAX_ATTACHMENTS_PER_TICKET <= 0:
            add("MAX_ATTACHMENTS_PER_TICKET must be positive")
        if self.MAX_TICKET_ATTACHMENT_BYTES <= 0:
            add("MAX_TICKET_ATTACHMENT_BYTES must be positive")
        if self.MAX_TICKET_ATTACHMENT_BYTES < self.MAX_UPLOAD_BYTES:
            add("MAX_TICKET_ATTACHMENT_BYTES must be at least MAX_UPLOAD_BYTES")
        if self.DB_POOL_SIZE <= 0 or self.DB_MAX_OVERFLOW < 0:
            add("Database pool size/overflow configuration is invalid")
        if self.DB_POOL_TIMEOUT_SECONDS <= 0 or self.DB_POOL_RECYCLE_SECONDS <= 0:
            add("Database pool timeout/recycle settings must be positive")
        if self.DB_CONNECT_TIMEOUT_SECONDS <= 0:
            add("DB_CONNECT_TIMEOUT_SECONDS must be positive")
        if self.MAX_MULTIPART_OVERHEAD_BYTES <= 0:
            add("MAX_MULTIPART_OVERHEAD_BYTES must be positive")

        if problems:
            raise RuntimeError(
                "Invalid production configuration: " + "; ".join(problems)
            )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
