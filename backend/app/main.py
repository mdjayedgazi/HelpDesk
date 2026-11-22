import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import (
    account_requests,
    admin,
    analytics,
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
from app.core.cache import (
    AnalyticsCacheInvalidationMiddleware,
    close_cache_client,
)
from app.core.config import settings
from app.core.database import create_session_and_tables
from app.core.health import readiness
from app.core.logging import configure_logging
from app.core.middleware import (
    AttachmentsDisabledMiddleware,
    BodySizeLimitMiddleware,
    SecurityHeadersMiddleware,
)
from app.core.rate_limit import (
    RateLimitUnavailable,
    close_rate_limit_store,
    ping_rate_limit_store,
)

configure_logging()

logger = logging.getLogger(__name__)


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

    # Reconcile the configured Owner once, at startup, after schema/tables are
    # available. This is deliberately best-effort: a deployment must never fail
    # (or delay readiness) because the designated person has not registered yet,
    # or because Clerk is briefly unreachable. The same reconciliation also runs
    # on every authenticated request, so a later sign-in still recognises them.
    await _reconcile_owner_on_startup()

    try:
        yield
    finally:
        await close_cache_client()
        await close_rate_limit_store()


async def _reconcile_owner_on_startup() -> None:
    """Best-effort Owner reconciliation at startup (never fatal)."""
    if settings.owner_email is None:
        return
    try:
        from app.core.auth import clerk_client
        from app.core.database import async_session
        from app.services.owner_identity import (
            find_candidate_by_email,
            reconcile_owner,
        )

        async with async_session() as session:
            candidate = await find_candidate_by_email(session, settings.owner_email)
            if candidate is None:
                logger.info(
                    "Owner reconciliation: designated account not registered yet; "
                    "ownership unchanged"
                )
                return
            decision = await reconcile_owner(
                session,
                clerk=clerk_client,
                candidate=candidate,
                configured_email=settings.owner_email,
            )
        logger.info("Owner reconciliation at startup: %s", decision.action.value)
    except Exception as exc:  # noqa: BLE001 - startup must stay available
        logger.warning(
            "Owner reconciliation at startup skipped (%s); ownership unchanged",
            type(exc).__name__,
        )


app = FastAPI(
    title="HelpDesk API",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
)

# Order matters: the body limiter is innermost so the security middleware adds
# headers to its 413, the attachment guard runs before multipart parsing, and
# CORS is outermost so browser clients can read errors including 413/429/503.
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(AttachmentsDisabledMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
# Invalidate the analytics cache after analytics-affecting writes. Added here so
# it runs inside the security/body middleware and cannot affect error shaping.
app.add_middleware(AnalyticsCacheInvalidationMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    # `Idempotency-Key` is sent by the frontend on ticket creation. Starlette
    # answers a cross-origin preflight with 400 unless every requested request
    # header is listed here, so omitting it breaks ticket creation whenever the
    # web app and API are on different origins (the normal production layout).
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "X-Request-ID",
        "Idempotency-Key",
    ],
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
app.include_router(analytics.router)
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
