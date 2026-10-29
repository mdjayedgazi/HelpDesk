import logging
import os
import re
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlmodel import select

from app.core.auth import user_dependency
from app.core.config import settings
from app.core.database import session_Dependency
from app.core.rate_limit import rate_limit
from app.enums.enums import AttachmentScanStatus
from app.models.attachment import Attachment
from app.schemas.attachments import AttachmentRead
from app.services.malware_scan import (
    MalwareScanner,
    ScannerError,
    get_malware_scanner,
)
from app.services.tickets import load_visible_ticket

logger = logging.getLogger(__name__)

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

# A client-provided MIME type is not evidence about the file's content. These
# signatures are a cheap first gate: they reject a renamed executable or a
# mismatched image/PDF, while still allowing the legacy text formats. Malware
# scanning/quarantine is a separate deployment concern (documented in
# data.md); signature checks are not a substitute for an antivirus engine.
_TEXT_CONTENT_TYPES = {"text/plain", "text/csv"}
_ZIP_CONTENT_TYPES = {
    "application/zip",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
_MAGIC_SIGNATURES = {
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "application/pdf": (b"%PDF-",),
    "application/msword": (b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1",),
}
_ZIP_SIGNATURES = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")
_HEADER_BYTES = 1024


def _matches_declared_type(content_type: str, header: bytes) -> bool:
    """Whether the first bytes are consistent with the declared content type.

    Text formats have no magic number; they must at least be NUL-free. Binary
    formats must carry their expected signature (ZIP-based Office documents use
    the ZIP signature). This deliberately does not attempt full document
    parsing or malware detection.
    """
    if content_type in _TEXT_CONTENT_TYPES:
        return b"\x00" not in header

    if content_type == "image/webp":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP"

    if content_type in _ZIP_CONTENT_TYPES:
        return any(header.startswith(signature) for signature in _ZIP_SIGNATURES)

    signatures = _MAGIC_SIGNATURES.get(content_type, ())
    return bool(signatures) and any(
        header.startswith(signature) for signature in signatures
    )


def _upload_root() -> Path:
    root = Path(settings.UPLOAD_DIR).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def _quarantine_root() -> Path:
    """Staging area that is never reachable through the download endpoint."""
    root = _upload_root() / ".quarantine"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_display_name(filename: str | None) -> str:
    name = os.path.basename(filename or "attachment")
    return re.sub(r"[^A-Za-z0-9._ -]", "_", name)[:255] or "attachment"


async def _ticket_attachment_totals(session, ticket_id: uuid.UUID) -> tuple[int, int]:
    """Return ``(count, total_bytes)`` for a ticket's stored attachments."""
    result = await session.exec(
        select(
            func.count(Attachment.id),
            func.coalesce(func.sum(Attachment.size_bytes), 0),
        ).where(Attachment.ticket_id == ticket_id)
    )
    count, total_bytes = result.one()
    return int(count), int(total_bytes)


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
    scanner: Annotated[MalwareScanner, Depends(get_malware_scanner)],
    _rate_limit: Annotated[None, Depends(rate_limit("attachment_upload"))],
) -> Attachment:
    """Upload, quarantine, scan, and only then publish an attachment."""
    # Locking the ticket serialises concurrent uploads to the same ticket, so
    # count/byte quotas cannot both be satisfied by racing requests.
    ticket = await load_visible_ticket(session, ticket_id, user, for_update=True)

    attachment_count, attachment_bytes = await _ticket_attachment_totals(
        session, ticket.id
    )
    if attachment_count >= settings.MAX_ATTACHMENTS_PER_TICKET:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="This ticket has reached its attachment count limit",
        )
    if attachment_bytes >= settings.MAX_TICKET_ATTACHMENT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="This ticket has reached its attachment storage limit",
        )
    remaining_ticket_bytes = settings.MAX_TICKET_ATTACHMENT_BYTES - attachment_bytes

    content_type = file.content_type or "application/octet-stream"
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type: {content_type}",
        )

    original_filename = _safe_display_name(file.filename)
    storage_key = f"{uuid.uuid4().hex}-{original_filename}"
    destination = _upload_root() / storage_key
    quarantined = _quarantine_root() / storage_key

    size = 0
    moved = False
    try:
        header = await file.read(_HEADER_BYTES)
        if not _matches_declared_type(content_type, header):
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail="File content does not match the declared content type",
            )

        size = len(header)
        if size > settings.MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="File is too large",
            )
        if size > remaining_ticket_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail="This ticket has reached its attachment storage limit",
            )

        with quarantined.open("wb") as out:
            out.write(header)
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.MAX_UPLOAD_BYTES or size > remaining_ticket_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=(
                            "File is too large"
                            if size > settings.MAX_UPLOAD_BYTES
                            else "This ticket has reached its attachment storage limit"
                        ),
                    )
                out.write(chunk)

        try:
            scan = await scanner.scan(quarantined)
        except ScannerError as exc:
            logger.warning("Attachment scanner unavailable: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Attachment scanning is temporarily unavailable",
                headers={"Retry-After": "5"},
            ) from None

        if scan.status is AttachmentScanStatus.INFECTED:
            logger.warning("Rejected an infected attachment (%s)", scan.detail)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="File failed malware scanning",
            )
        if scan.status is not AttachmentScanStatus.CLEAN:
            # A scanner must explicitly say CLEAN. PENDING/unknown is a failure.
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Attachment scanning did not return a clean result",
                headers={"Retry-After": "5"},
            )

        os.replace(quarantined, destination)
        moved = True
    except HTTPException:
        quarantined.unlink(missing_ok=True)
        if moved:
            destination.unlink(missing_ok=True)
        raise
    except Exception:
        quarantined.unlink(missing_ok=True)
        if moved:
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
        scan_status=AttachmentScanStatus.CLEAN,
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
    scanner: Annotated[MalwareScanner, Depends(get_malware_scanner)],
) -> FileResponse:
    """Download a stored attachment if the user may view its ticket.

    Legacy ``PENDING`` files are rescanned on demand. A file is served only
    after an explicit CLEAN result; scanner errors remain fail-closed.
    """
    attachment = await session.get(Attachment, attachment_id)
    if attachment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment not found",
        )

    # Authorize before taking any lock, so a caller who cannot see the ticket
    # can never hold a row lock on its attachments.
    await load_visible_ticket(session, attachment.ticket_id, user)

    if attachment.scan_status is AttachmentScanStatus.PENDING:
        # Only a legacy rescan mutates the row. Lock it for that case alone and
        # re-read the status, because a concurrent download may have finished
        # the rescan first. CLEAN downloads stay lock-free.
        await session.refresh(attachment, with_for_update=True)

    root = _upload_root()
    path = (root / attachment.storage_key).resolve()
    if root not in path.parents or not path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment file not found",
        )

    if attachment.scan_status is AttachmentScanStatus.INFECTED:
        # Do not confirm an infected file's existence or serve its bytes.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attachment file not found",
        )

    if attachment.scan_status is AttachmentScanStatus.PENDING:
        try:
            scan = await scanner.scan(path)
        except ScannerError as exc:
            logger.warning("Attachment rescan unavailable: %s", exc)
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Attachment scanning is temporarily unavailable",
                headers={"Retry-After": "5"},
            ) from None

        if scan.status is AttachmentScanStatus.CLEAN:
            attachment.scan_status = AttachmentScanStatus.CLEAN
            session.add(attachment)
            await session.commit()
        elif scan.status is AttachmentScanStatus.INFECTED:
            path.unlink(missing_ok=True)
            attachment.scan_status = AttachmentScanStatus.INFECTED
            session.add(attachment)
            await session.commit()
            logger.warning(
                "Rejected a legacy infected attachment (%s)",
                scan.detail or "unknown signature",
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Attachment file not found",
            )
        else:
            # A scanner must explicitly say CLEAN. PENDING/unknown is a failure.
            await session.rollback()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Attachment scanning did not return a clean result",
                headers={"Retry-After": "5"},
            )

    if attachment.scan_status is not AttachmentScanStatus.CLEAN:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Attachment is still awaiting a clean malware scan",
        )

    # FileResponse with a filename sends Content-Disposition: attachment, so
    # the browser downloads the file instead of rendering it inline.
    return FileResponse(
        path=path,
        media_type=attachment.content_type,
        filename=attachment.original_filename,
        headers={"X-Content-Type-Options": "nosniff"},
    )
