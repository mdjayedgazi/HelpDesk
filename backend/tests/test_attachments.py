from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.enums import AttachmentScanStatus
from app.main import app
from app.models.attachment import Attachment
from app.services.malware_scan import (
    ScannerTimeout,
    ScannerUnavailable,
    ScanResult,
    get_malware_scanner,
)


def _published_files(root: Path) -> list[Path]:
    """Files the download endpoint could serve, excluding the quarantine dir."""
    return [path for path in root.iterdir() if path.name != ".quarantine"]


def _quarantined_files(root: Path) -> list[Path]:
    quarantine = root / ".quarantine"
    return list(quarantine.iterdir()) if quarantine.exists() else []


class StubScanner:
    def __init__(self, *, result=None, error=None):
        self.result = result
        self.error = error

    async def scan(self, path):
        if self.error is not None:
            raise self.error
        return self.result


@pytest.mark.asyncio
async def test_customer_uploads_and_downloads_attachment(
    client, make_user, make_ticket
):
    customer = await make_user()
    ticket = await make_ticket(customer)

    upload = await client.post(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers={"X-Test-User": customer.username},
        files={"file": ("note.txt", b"hello world", "text/plain")},
    )
    assert upload.status_code == 201
    body = upload.json()
    assert body["original_filename"] == "note.txt"
    assert body["size_bytes"] == 11
    assert body["scan_status"] == "CLEAN"
    assert "storage_key" not in body

    listing = await client.get(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers={"X-Test-User": customer.username},
    )
    assert listing.status_code == 200
    assert len(listing.json()) == 1

    download = await client.get(
        f"/api/v1/attachments/{body['id']}/download",
        headers={"X-Test-User": customer.username},
    )
    assert download.status_code == 200
    assert download.content == b"hello world"


@pytest.mark.asyncio
async def test_unsupported_content_type_rejected(client, make_user, make_ticket):
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers={"X-Test-User": customer.username},
        files={"file": ("evil.exe", b"MZ", "application/x-msdownload")},
    )
    assert response.status_code == 415


@pytest.mark.asyncio
async def test_declared_image_with_non_image_content_is_rejected(
    client, make_user, make_ticket
):
    """MIME/extension alone must not smuggle non-image bytes through."""
    from app.core.config import settings

    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers={"X-Test-User": customer.username},
        files={"file": ("photo.png", b"#!/bin/sh\necho not an image\n", "image/png")},
    )
    assert response.status_code == 415
    upload_dir = Path(settings.UPLOAD_DIR)
    assert _published_files(upload_dir) == []
    assert _quarantined_files(upload_dir) == []


@pytest.mark.asyncio
async def test_declared_text_with_nul_bytes_is_rejected(client, make_user, make_ticket):
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers={"X-Test-User": customer.username},
        files={"file": ("binary.txt", b"text\x00binary", "text/plain")},
    )
    assert response.status_code == 415


@pytest.mark.asyncio
async def test_pdf_signature_is_accepted_and_download_is_nosniff(
    client, make_user, make_ticket
):
    customer = await make_user()
    ticket = await make_ticket(customer)
    pdf = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"

    upload = await client.post(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers={"X-Test-User": customer.username},
        files={"file": ("document.pdf", pdf, "application/pdf")},
    )
    assert upload.status_code == 201

    download = await client.get(
        f"/api/v1/attachments/{upload.json()['id']}/download",
        headers={"X-Test-User": customer.username},
    )
    assert download.status_code == 200
    assert download.headers["x-content-type-options"] == "nosniff"
    assert download.headers["content-disposition"].startswith("attachment;")


@pytest.mark.asyncio
async def test_cannot_upload_to_foreign_ticket(client, make_user, make_ticket):
    alice = await make_user()
    bob = await make_user()
    ticket = await make_ticket(bob)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers={"X-Test-User": alice.username},
        files={"file": ("note.txt", b"nope", "text/plain")},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_upload_removes_file_when_commit_fails(
    client_no_raise, make_user, make_ticket, monkeypatch
):
    """A failed database commit must not leave an orphaned file on disk."""
    from app.core.config import settings

    customer = await make_user()
    ticket = await make_ticket(customer)

    async def failing_commit(self):
        raise RuntimeError("database commit failed")

    monkeypatch.setattr(AsyncSession, "commit", failing_commit)

    response = await client_no_raise.post(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers={"X-Test-User": customer.username},
        files={"file": ("note.txt", b"hello world", "text/plain")},
    )
    assert response.status_code == 500

    upload_dir = Path(settings.UPLOAD_DIR)
    assert _published_files(upload_dir) == []
    assert _quarantined_files(upload_dir) == []


@pytest.mark.asyncio
async def test_infected_upload_is_rejected_and_never_published(
    client, make_user, make_ticket
):
    from app.core.config import settings

    app.dependency_overrides[get_malware_scanner] = lambda: StubScanner(
        result=ScanResult(
            status=AttachmentScanStatus.INFECTED,
            detail="Eicar-Test-Signature",
        )
    )
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers={"X-Test-User": customer.username},
        files={"file": ("note.txt", b"harmless fixture", "text/plain")},
    )

    assert response.status_code == 422
    upload_dir = Path(settings.UPLOAD_DIR)
    assert _published_files(upload_dir) == []
    assert _quarantined_files(upload_dir) == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [ScannerUnavailable("scanner down"), ScannerTimeout("scanner timed out")],
)
async def test_scanner_failure_is_fail_closed_and_cleans_up(
    client, make_user, make_ticket, error
):
    from app.core.config import settings

    app.dependency_overrides[get_malware_scanner] = lambda: StubScanner(error=error)
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers={"X-Test-User": customer.username},
        files={"file": ("note.txt", b"harmless fixture", "text/plain")},
    )

    assert response.status_code == 503
    assert response.headers["retry-after"] == "5"
    upload_dir = Path(settings.UPLOAD_DIR)
    assert _published_files(upload_dir) == []
    assert _quarantined_files(upload_dir) == []


@pytest.mark.asyncio
async def test_unknown_scan_result_is_not_treated_as_clean(
    client, make_user, make_ticket
):
    from app.core.config import settings

    app.dependency_overrides[get_malware_scanner] = lambda: StubScanner(
        result=ScanResult(status=AttachmentScanStatus.PENDING)
    )
    customer = await make_user()
    ticket = await make_ticket(customer)

    response = await client.post(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers={"X-Test-User": customer.username},
        files={"file": ("note.txt", b"harmless fixture", "text/plain")},
    )

    assert response.status_code == 503
    upload_dir = Path(settings.UPLOAD_DIR)
    assert _published_files(upload_dir) == []
    assert _quarantined_files(upload_dir) == []


async def _make_attachment(
    session_factory,
    *,
    customer,
    ticket,
    scan_status,
    storage_key,
):
    from app.core.config import settings

    root = Path(settings.UPLOAD_DIR)
    root.mkdir(parents=True, exist_ok=True)
    (root / storage_key).write_bytes(b"fixture")
    async with session_factory() as session:
        attachment = Attachment(
            ticket_id=ticket.id,
            uploaded_by_user_id=customer.id,
            original_filename=storage_key,
            storage_key=storage_key,
            content_type="text/plain",
            size_bytes=7,
            scan_status=scan_status,
        )
        session.add(attachment)
        await session.commit()
        await session.refresh(attachment)
    return attachment


@pytest.mark.asyncio
async def test_pending_attachment_is_rescanned_before_download(
    client, session_factory, make_user, make_ticket
):
    customer = await make_user()
    ticket = await make_ticket(customer)
    attachment = await _make_attachment(
        session_factory,
        customer=customer,
        ticket=ticket,
        scan_status=AttachmentScanStatus.PENDING,
        storage_key="pending-note.txt",
    )

    response = await client.get(
        f"/api/v1/attachments/{attachment.id}/download",
        headers={"X-Test-User": customer.username},
    )

    assert response.status_code == 200
    assert response.content == b"fixture"

    async with session_factory() as session:
        stored = await session.get(Attachment, attachment.id)
    assert stored is not None
    assert stored.scan_status is AttachmentScanStatus.CLEAN


@pytest.mark.asyncio
async def test_pending_attachment_fails_closed_when_rescan_unavailable(
    client, session_factory, make_user, make_ticket
):
    app.dependency_overrides[get_malware_scanner] = lambda: StubScanner(
        error=ScannerUnavailable("scanner offline")
    )
    customer = await make_user()
    ticket = await make_ticket(customer)
    attachment = await _make_attachment(
        session_factory,
        customer=customer,
        ticket=ticket,
        scan_status=AttachmentScanStatus.PENDING,
        storage_key="pending-offline.txt",
    )

    response = await client.get(
        f"/api/v1/attachments/{attachment.id}/download",
        headers={"X-Test-User": customer.username},
    )

    assert response.status_code == 503
    async with session_factory() as session:
        stored = await session.get(Attachment, attachment.id)
    assert stored is not None
    assert stored.scan_status is AttachmentScanStatus.PENDING


@pytest.mark.asyncio
async def test_infected_attachment_is_not_served(
    client, session_factory, make_user, make_ticket
):
    customer = await make_user()
    ticket = await make_ticket(customer)
    attachment = await _make_attachment(
        session_factory,
        customer=customer,
        ticket=ticket,
        scan_status=AttachmentScanStatus.INFECTED,
        storage_key="infected-note.txt",
    )

    response = await client.get(
        f"/api/v1/attachments/{attachment.id}/download",
        headers={"X-Test-User": customer.username},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_unauthorized_user_cannot_download_attachment(
    client, make_user, make_ticket
):
    owner = await make_user()
    outsider = await make_user()
    ticket = await make_ticket(owner)

    upload = await client.post(
        f"/api/v1/tickets/{ticket.id}/attachments",
        headers={"X-Test-User": owner.username},
        files={"file": ("note.txt", b"private", "text/plain")},
    )
    assert upload.status_code == 201

    response = await client.get(
        f"/api/v1/attachments/{upload.json()['id']}/download",
        headers={"X-Test-User": outsider.username},
    )

    assert response.status_code == 404
