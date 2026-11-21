"""The justified list-ordering indexes exist and the model matches them.

These tests assert the metadata that Alembic compares against; they do not open
a database. The migration itself is exercised by the CI disposable-PostgreSQL
migration job.
"""

from sqlalchemy import Index

from app.models.notification import Notification
from app.models.ticket import Ticket


def _index_names(model) -> set[str]:
    return {
        index.name
        for index in model.__table__.indexes
        if isinstance(index, Index) and index.name
    }


def test_tickets_created_at_index_is_declared():
    assert "ix_tickets_created_at" in _index_names(Ticket)


def test_notifications_recipient_created_at_index_is_declared():
    assert "ix_notifications_recipient_created_at" in _index_names(Notification)


def test_notification_index_columns_lead_with_recipient():
    index = next(
        index
        for index in Notification.__table__.indexes
        if index.name == "ix_notifications_recipient_created_at"
    )
    assert [column.name for column in index.columns] == [
        "recipient_user_id",
        "created_at",
    ]


def test_idempotency_index_is_unique_and_partial():
    index = next(
        index
        for index in Ticket.__table__.indexes
        if index.name == "uq_tickets_creator_request_key"
    )
    assert index.unique is True
    assert [column.name for column in index.columns] == [
        "created_by_user_id",
        "client_request_id",
    ]
    # The partial predicate keeps ordinary key-less ticket rows out of the
    # unique constraint, so existing data and normal requests are unaffected.
    assert index.dialect_options["postgresql"]["where"] is not None
    assert index.dialect_options["sqlite"]["where"] is not None


def test_no_duplicate_index_on_the_same_columns():
    """Each declared index must be on a distinct column set per table."""
    for model in (Ticket, Notification):
        seen: set[tuple[str, ...]] = set()
        for index in model.__table__.indexes:
            if not isinstance(index, Index) or not index.name:
                continue
            columns = tuple(column.name for column in index.columns)
            # Single-column indexes mirroring a declared unique/foreign-key
            # shortcut are created by SQLModel itself and are intentionally
            # left alone; only compare our multi-column declarations here.
            if len(columns) < 2:
                continue
            assert columns not in seen, (
                f"{model.__tablename__} has two indexes on {columns}"
            )
            seen.add(columns)


def test_migration_0011_skips_an_already_indexed_column_set(monkeypatch):
    """An operator may pre-create the index concurrently (or under another name).

    ``CREATE INDEX CONCURRENTLY`` cannot run inside Alembic's transaction, so
    the documented large-table path pre-creates it. ``upgrade`` must then not
    attempt a duplicate create, which would fail on the existing name.
    """
    from importlib import import_module

    migration = import_module("migrations.versions.0011_query_indexes")

    created: list[tuple[str, str, list[str]]] = []

    class _Inspector:
        def get_indexes(self, _table):
            return [{"name": "pre_created", "column_names": ["created_at"]}]

    class _Bind:
        pass

    monkeypatch.setattr(migration.sa, "inspect", lambda _bind: _Inspector())
    monkeypatch.setattr(migration.op, "get_bind", lambda: _Bind())

    def _record(name, table, columns, **_kwargs):
        created.append((name, table, columns))

    monkeypatch.setattr(migration.op, "create_index", _record)

    migration.upgrade()

    created_tables = {table for _name, table, _columns in created}
    # ``tickets.created_at`` is already indexed, so it is skipped...
    assert "tickets" not in created_tables
    # ...while the still-missing notification index is created.
    assert ("ix_notifications_recipient_created_at", "notifications") in {
        (name, table) for name, table, _columns in created
    }
