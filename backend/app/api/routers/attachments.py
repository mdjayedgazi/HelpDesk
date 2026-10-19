import os
import re
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlmodel import select

from app.core.auth import user_dependency
from app.core.config import settings
from app.core.database import session_Dependency
from app.models.attachment import Attachment
from app.schemas.attachments import AttachmentRead
from app.services.tickets import load_visible_ticket

router = APIRouter(tags=["attachments"])

# Only these content types may be uploaded. Everything else is rejected so the
# server never stores arbitrary executables.
ALLOWED_CONTENT_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "application/pdf",
    "text/plain",
    "text/csv",
    "application/zip",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _upload_root() -> Path:
    root = Path(settings.UPLOAD_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_display_name(filename: str | None) -> str:
    name = os.path.basename(filename or "attachment")
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:255] or "attachment"


@router.get(
    "/api/v1/tickets/{ticket_id}/attachments",
    response_model=list[AttachmentRead],
)
async def list_attachments(
    ticket_id: uuid.UUID,
    session: session_Dependency,
    user: user_dependency,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Attachment]:
    await load_visible_ticket(session, ticket_id, user)
    statement = (
        select(Attachment)
        .where(Attachment.ticket_id == ticket_id)
        .order_by(Attachment.created_at.asc())
        .limit(limit)
        .offset(offset)
    )
    result = await session.exec(statement)
    return list(result.all())


@router.post(
    "/api/v1/tickets/{ticket_id}/attachments",
    response_model=AttachmentRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_attachment(
    ticket_id: uuid.UUID,
    session: session_Dependency,
    user: user_dependency,
    file: Annotated[UploadFile, File()],
) -> Attachment:
    """Upload a file and store its metadata against the ticket."""
    await load_visible_ticket(session, ticket_id, user)

    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type: {content_type}",
        )

    original_filename = _safe_display_name(file.filename)
    storage_key = f"{uuid.uuid4().hex}-{original_filename}"
    destination = _upload_root() / storage_key

    size = 0
    try:
        with destination.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail="File is too large",
                    )
                out.write(chunk)
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    attachment = Attachment(
        ticket_id=ticket_id,
        uploaded_by_user_id=user.id,
        original_filename=original_filename,
        storage_key=storage_key,
        content_type=content_type,
        size_bytes=size,
    )
    session.add(attachment)
    try:
        await session.commit()
    except Exception:
        # The row was not stored, so the file on disk would be an orphan.
        # Only ever remove the file we just wrote in this request.
        await session.rollback()
        destination.unlink(missing_ok=True)
        raise
    await session.refresh(attachment)
    return attachment


@router.get("/api/v1/attachments/{attachment_id}/download")
async def download_attachment(
    attachment_id: uuid.UUID,
    session: session_Dependency,
    user: user_dependency,
) -> FileResponse:
    """Download a stored attachment if the user may view its ticket."""
    attachment = await session.get(Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found",
        )

    await load_visible_ticket(session, attachment.ticket_id, user)

    root = _upload_root()
    path = (root / attachment.storage_key).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment file not found",
        )

    # FileResponse with a filename sends Content-Disposition: attachment, so
    # the browser downloads the file instead of rendering it inline.
    return FileResponse(
        path=path,
        media_type=attachment.content_type,
        filename=attachment.original_filename,
    )
