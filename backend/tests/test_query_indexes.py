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
