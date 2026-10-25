"""Rescan attachments that predate malware scanning.

Migration ``0009`` deliberately marks every existing attachment ``PENDING``.
Those files are not downloadable. Run this command once a ClamAV scanner is
configured to promote clean files to ``CLEAN`` and mark infected files
``INFECTED`` (deleting their bytes from the upload root).

Usage (from ``backend/``)::

    uv run python -m app.commands.scan_attachments

The command is fail-closed: if the scanner is not configured or becomes
unavailable, it stops with a non-zero exit code and leaves the remaining rows
``PENDING``. It never treats an error as a clean result.
"""

import asyncio
import sys
from pathlib import Path

from sqlmodel import select

from app.core.config import settings
from app.core.database import async_session, engine
from app.enums.enums import AttachmentScanStatus
from app.models.attachment import Attachment
from app.services.malware_scan import ScannerError, get_malware_scanner


async def scan_pending() -> int:
    if not settings.MALWARE_SCAN_ENABLED or not settings.CLAMAV_HOST:
        print(
            "Malware scanning is not configured. Set MALWARE_SCAN_ENABLED=true "
            "and CLAMAV_HOST before rescanning attachments.",
            file=sys.stderr,
        )
        return 2

    scanner = get_malware_scanner()
    root = Path(settings.UPLOAD_DIR).resolve()
    clean = 0
    infected = 0
    missing = 0

    try:
        async with async_session() as session:
            attachments = (
                await session.exec(
                    select(Attachment).where(
                        Attachment.scan_status == AttachmentScanStatus.PENDING
                    )
                )
            ).all()

            for attachment in attachments:
                path = (root / attachment.storage_key).resolve()
                if root not in path.parents or not path.is_file():
                    print(
                        f"missing: {attachment.id} ({attachment.storage_key})",
                        file=sys.stderr,
                    )
                    missing += 1
                    continue

                try:
                    result = await scanner.scan(path)
                except ScannerError as exc:
                    await session.rollback()
                    print(f"scanner unavailable: {exc}", file=sys.stderr)
                    return 1

                if result.status is AttachmentScanStatus.CLEAN:
                    attachment.scan_status = AttachmentScanStatus.CLEAN
                    clean += 1
                elif result.status is AttachmentScanStatus.INFECTED:
                    path.unlink(missing_ok=True)
                    attachment.scan_status = AttachmentScanStatus.INFECTED
                    infected += 1
                    print(
                        f"infected: {attachment.id} ({result.detail or 'unknown'})",
                        file=sys.stderr,
                    )
                else:
                    await session.rollback()
                    print(
                        f"unknown scan result for {attachment.id}; stopping",
                        file=sys.stderr,
                    )
                    return 1

                await session.commit()

        print(f"clean={clean} infected={infected} missing={missing}")
        return 0
    finally:
        await engine.dispose()


def main() -> None:
    raise SystemExit(asyncio.run(scan_pending()))


if __name__ == "__main__":
    main()
