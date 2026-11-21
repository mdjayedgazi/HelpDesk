"""Guard for opt-in PostgreSQL test suites.

Every PostgreSQL test module creates tables and rows in the database it is
pointed at. The guard must therefore decide from the **database name**, never
from the whole URL: a production URL can contain ``ci`` in its username,
password, or host (for example ``ci_runner@db.example.com/helpdesk``) and must
still be refused.

``HD_TEST_POSTGRES_URL`` / ``HD_DEMO_SEED_POSTGRES_URL`` are only honoured when
the target database name contains one of the accepted disposable markers.
"""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlsplit

ACCEPTED_MARKERS = ("test", "verify", "ci", "demo", "disposable")


def database_name(url: str | None) -> str | None:
    """Return the database name from a SQLAlchemy/libpq URL, or ``None``."""
    if not url:
        return None
    try:
        parsed = urlsplit(url)
    except ValueError:
        return None

    # ``postgresql+psycopg://`` is a SQLAlchemy URL; libpq also accepts
    # ``?dbname=`` for some tools, so check the query string first.
    query_dbname = parse_qs(parsed.query).get("dbname")
    if query_dbname:
        return unquote(query_dbname[0]).strip() or None

    name = parsed.path.lstrip("/").strip()
    return unquote(name) or None


def is_disposable(url: str | None, markers: tuple[str, ...] = ACCEPTED_MARKERS) -> bool:
    """Whether ``url`` points at an obviously disposable database."""
    name = database_name(url)
    if not name:
        return False
    lowered = name.lower()
    return any(marker in lowered for marker in markers)
