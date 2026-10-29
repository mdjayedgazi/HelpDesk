"""HTTP hardening middleware: request limits, security headers, request IDs.

The body limiter runs *before* FastAPI parses JSON or multipart data. It rejects
an oversized ``Content-Length`` immediately and, for chunked/unknown-length
bodies, stops reading as soon as the configured cap is crossed. Only a bounded
request is replayed to the application.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import settings

logger = logging.getLogger("app.request")

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_BODY_METHODS = {"POST", "PUT", "PATCH"}
_DOCS_PATHS = ("/docs", "/redoc")

# Swagger UI/ReDoc are only reachable in development/test (production disables
# the routes). They need the FastAPI CDN assets; API responses do not.
_DOCS_CSP = (
    "default-src 'none'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; "
    "form-action 'none'"
)
_API_CSP = (
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; "
    "form-action 'none'; object-src 'none'"
)


def _body_limit(content_type: str) -> int:
    if content_type.lower().startswith("multipart/form-data"):
        return settings.max_upload_request_bytes
    return settings.MAX_JSON_BODY_BYTES


async def _send_json(
    send: Send,
    status_code: int,
    detail: str,
    *,
    headers: Iterable[tuple[bytes, bytes]] = (),
) -> None:
    body = json.dumps({"detail": detail}).encode("utf-8")
    response_headers = [
        (b"content-type", b"application/json"),
        (b"content-length", str(len(body)).encode("ascii")),
        *headers,
    ]
    await send(
        {
            "type": "http.response.start",
            "status": status_code,
            "headers": response_headers,
        }
    )
    await send({"type": "http.response.body", "body": body})


class BodySizeLimitMiddleware:
    """Reject oversized request bodies before application parsing."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] not in _BODY_METHODS:
            await self.app(scope, receive, send)
            return

        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        limit = _body_limit(headers.get("content-type", ""))

        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                await _send_json(send, 400, "Invalid Content-Length header")
                return
            if declared < 0:
                await _send_json(send, 400, "Invalid Content-Length header")
                return
            if declared > limit:
                await _send_json(
                    send,
                    413,
                    "Request body is too large",
                    headers=[(b"connection", b"close")],
                )
                return

        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > limit:
                await _send_json(
                    send,
                    413,
                    "Request body is too large",
                    headers=[(b"connection", b"close")],
                )
                return
            if chunk:
                chunks.append(chunk)
            if not message.get("more_body", False):
                break

        body = b"".join(chunks)
        replayed = False

        async def replay() -> Message:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        await self.app(scope, replay, send)


class SecurityHeadersMiddleware:
    """Add security headers, no-store caching, and request correlation IDs."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        headers = {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }
        supplied_request_id = headers.get("x-request-id", "")
        request_id = (
            supplied_request_id
            if _REQUEST_ID_RE.fullmatch(supplied_request_id)
            else uuid.uuid4().hex
        )
        scope["state"] = {**scope.get("state", {}), "request_id": request_id}
        started = time.perf_counter()
        status_code: int | None = None

        async def send_with_headers(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                extra = [
                    (b"x-content-type-options", b"nosniff"),
                    (b"x-frame-options", b"DENY"),
                    (b"referrer-policy", b"no-referrer"),
                    (
                        b"permissions-policy",
                        b"camera=(), microphone=(), geolocation=(), payment=(), usb=()",
                    ),
                    (b"cross-origin-opener-policy", b"same-origin"),
                    (b"x-request-id", request_id.encode("ascii")),
                ]
                if path.startswith(_DOCS_PATHS):
                    extra.append(
                        (b"content-security-policy", _DOCS_CSP.encode("ascii"))
                    )
                else:
                    extra.append((b"content-security-policy", _API_CSP.encode("ascii")))

                if path.startswith("/api/") or path.startswith(_DOCS_PATHS):
                    extra.extend(
                        [
                            (b"cache-control", b"no-store"),
                            (b"pragma", b"no-cache"),
                        ]
                    )
                if settings.HSTS_ENABLED:
                    extra.append(
                        (
                            b"strict-transport-security",
                            f"max-age={settings.HSTS_MAX_AGE_SECONDS}; includeSubDomains".encode(
                                "ascii"
                            ),
                        )
                    )

                # Keep every application header, including repeated ones such as
                # Set-Cookie or Vary, and only add defaults that are absent.
                response_headers = list(message.get("headers", []))
                present = {key.lower() for key, _ in response_headers}
                response_headers.extend(
                    (key, value) for key, value in extra if key not in present
                )
                message["headers"] = response_headers

            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        finally:
            duration_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "%s %s %s %.1fms",
                scope.get("method", "-"),
                path,
                status_code if status_code is not None else 500,
                duration_ms,
                extra={"request_id": request_id},
            )
