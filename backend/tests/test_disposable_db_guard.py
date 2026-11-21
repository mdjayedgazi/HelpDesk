"""The opt-in PostgreSQL suites must refuse a production-looking URL.

The previous guard searched the whole URL for ``test``/``verify``/``ci``, so a
URL such as ``postgresql+psycopg://ci_runner:pw@db.example.com/helpdesk`` passed
even though its database is ``helpdesk``. These tests lock in the database-name
check that replaced it.
"""

from tests._disposable_db_guard import database_name, is_disposable


def test_production_url_with_ci_in_the_username_is_rejected():
    url = "postgresql+psycopg://ci_runner:secret@db.example.com/helpdesk"
    assert database_name(url) == "helpdesk"
    assert is_disposable(url) is False


def test_production_url_with_test_in_the_password_is_rejected():
    url = "postgresql+psycopg://app:verify-me@db.example.com/production"
    assert is_disposable(url) is False


def test_disposable_database_names_are_accepted():
    for name in ("hdverify", "migrate_verify", "helpdesk_demo_verify", "hd_ci"):
        url = f"postgresql+psycopg://verify:verify@127.0.0.1:5432/{name}"
        assert is_disposable(url) is True, name


def test_query_string_dbname_is_honoured():
    url = "postgresql+psycopg://u:p@db.example.com/?dbname=hdverify"
    assert database_name(url) == "hdverify"
    assert is_disposable(url) is True


def test_missing_or_empty_url_is_rejected():
    assert is_disposable(None) is False
    assert is_disposable("") is False
    assert is_disposable("postgresql+psycopg://u:p@db.example.com/") is False
