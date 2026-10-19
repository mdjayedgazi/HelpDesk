from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


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
    remaining = list(upload_dir.iterdir()) if upload_dir.exists() else []
    assert remaining == []
