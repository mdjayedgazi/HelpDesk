from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import (
    account_requests,
    admin,
    attachments,
    comments,
    internal_messages,
    notifications,
    staff_messages,
    ticket_feedback,
    ticket_history,
    tickets,
    users,
)
from app.core.config import settings
from app.core.database import create_session_and_tables
from app.core.health import readiness
from app.core.logging import configure_logging
from app.core.middleware import BodySizeLimitMiddleware, SecurityHeadersMiddleware
from app.core.rate_limit import (
    RateLimitUnavailable,
    close_rate_limit_store,
    ping_rate_limit_store,
)

configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Creating tables on startup is convenient for local development. Turn it
    # off (the default) in real deployments and use migrations instead.
    if settings.AUTO_CREATE_TABLES:
        await create_session_and_tables()

    # Production refuses to start with an unusable shared rate limiter rather
    # than failing every protected request one at a time. Configuration shape
    # is already validated by Settings; this checks reachability.
    if settings.RATE_LIMIT_ENABLED:
        try:
            await ping_rate_limit_store()
        except RateLimitUnavailable as exc:
            raise RuntimeError(
                "The configured Redis rate-limit store is unreachable"
            ) from exc

    try:
        yield
    finally:
        await close_rate_limit_store()


app = FastAPI(
    title="HelpDesk API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

# Order matters: the body limiter is innermost so the security middleware adds
# headers to its 413, and CORS is outermost so browser clients can read errors
# including 413/429/503.
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "X-Request-ID"],
    expose_headers=[
        "X-Request-ID",
        "Retry-After",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    ],
)

app.include_router(users.router)
app.include_router(tickets.router)
app.include_router(comments.router)
app.include_router(attachments.router)
app.include_router(ticket_history.router)
app.include_router(ticket_feedback.router)
app.include_router(notifications.router)
app.include_router(admin.router)
app.include_router(staff_messages.router)
app.include_router(account_requests.router)
app.include_router(internal_messages.router)


@app.get("/health", tags=["health"], include_in_schema=False)
@app.get("/health/live", tags=["health"])
async def health_live() -> dict[str, str]:
    """Process liveness only. Railway uses this while starting a deployment."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def health_ready(response: Response) -> dict[str, object]:
    """Dependency readiness for PostgreSQL and enabled abuse-control services."""
    healthy, checks = await readiness()
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {
        "status": "ready" if healthy else "unavailable",
        "checks": checks,
    }
