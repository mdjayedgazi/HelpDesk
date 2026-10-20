from contextlib import asynccontextmanager

from fastapi import FastAPI
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Creating tables on startup is convenient for local development. Turn it
    # off (the default) in real deployments and use migrations instead.
    if settings.AUTO_CREATE_TABLES:
        await create_session_and_tables()
    yield


app = FastAPI(
    title="HelpDesk API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
