"""Structured, redacted application logging.

The API never logs request bodies, authorization headers, cookies, or query
strings. This module adds a second safety net for exception/error messages that
might embed a secret, plus a JSON formatter suitable for Railway log capture.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime

from app.core.config import settings

_CONFIGURED_MARKER = "_helpdesk_configured"

_REDACTIONS = (
    (
        re.compile(r"(?i)(authorization:\s*bearer\s+)[^\s,;]+"),
        r"\1[REDACTED]",
    ),
    (re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9_-]+"), "sk_[REDACTED]"),
    (
        re.compile(r"(?i)(postgres(?:ql)?(?:\+[a-z0-9]+)?://[^:\s/@]+:)[^@\s]+@"),
        r"\1[REDACTED]@",
    ),
    (re.compile(r"(?i)(redis(?:s)?://[^:\s/@]+:)[^@\s]+@"), r"\1[REDACTED]@"),
    (
        re.compile(
            r"(?i)\b(password|secret|token|api[_-]?key|client[_-]?secret)"
            r"(\s*[=:]\s*)[^\s,;]+"
        ),
        r"\1\2[REDACTED]",
    ),
)


def redact(value: str) -> str:
    for pattern, replacement in _REDACTIONS:
        value = pattern.sub(replacement, value)
    return value


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - malformed log records must not break logging
            return True
        record.msg = redact(message)
        record.args = ()
        if record.exc_text:
            record.exc_text = redact(record.exc_text)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact(record.getMessage()),
        }
        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = request_id
        if record.exc_info:
            payload["exception"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, separators=(",", ":"), default=str)


class HumanFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        return redact(message)


def configure_logging() -> None:
    """Configure the root logger once, without leaking framework debug logs."""
    root = logging.getLogger()
    if any(getattr(handler, _CONFIGURED_MARKER, False) for handler in root.handlers):
        return

    handler = logging.StreamHandler(sys.stdout)
    setattr(handler, _CONFIGURED_MARKER, True)
    handler.addFilter(RedactionFilter())
    if settings.log_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            HumanFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )

    root.handlers = [handler]
    root.setLevel(settings.LOG_LEVEL.upper())
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
