# Database migrations (Alembic)

The backend uses [Alembic](https://alembic.sqlalchemy.org/) for schema
changes. The database URL is read from the application settings
(`DATABASE_URL` in `backend/.env`), so there is only one source of truth.

All commands below are run from the `backend/` directory with the project
virtual environment active (for example `uv run alembic ...` or
`.venv/bin/alembic ...`).

## Apply migrations to a new, empty PostgreSQL database

1. Point `DATABASE_URL` at the empty database, e.g.
   `postgresql+psycopg://user:password@localhost:5432/helpdesk`.
2. Make sure `AUTO_CREATE_TABLES` stays `false`. The schema is owned by
   Alembic, not by application startup.
3. Apply every migration:

   ```bash
   alembic upgrade head
   ```

## Inspect the current revision

```bash
# What revision is the database on?
alembic current

# Full history, with the current revision marked.
alembic history --verbose

# Preview the SQL for the next migration without touching the database.
alembic upgrade head --sql
```

`alembic upgrade head --sql` runs in *offline* mode: it renders SQL to stdout
and never opens a connection, so it is safe to review on any machine.

## Create a new migration

```bash
# Autogenerate a revision by comparing the models with the live database.
alembic revision --autogenerate -m "describe the change"

# Always read the generated file before applying it. Autogenerate does not
# detect every change (enum value edits, some constraint renames).
```

## Adopting an existing database (baseline)

If a database already has these tables but no `alembic_version` row (for
example it was created earlier with `AUTO_CREATE_TABLES=true`), do **not**
run `alembic upgrade head` blindly and do not stamp it automatically:

1. Confirm the live schema matches `migrations/versions/0001_initial_schema.py`
   (compare the tables, columns, indexes and constraints).
2. Only once they match, mark the database as already at that revision:

   ```bash
   alembic stamp 0001_initial
   ```

3. From then on, apply subsequent migrations normally with
   `alembic upgrade head`.

`stamp` records a revision without running it. Stamping a database whose schema
does **not** match a revision will hide real differences, so verify first.

## Downgrade

```bash
alembic downgrade -1
```

The initial migration's `downgrade` drops every table (and the PostgreSQL enums)
and therefore **destroys all data**. Treat it as a convenience for disposable
databases; it is not a data-preserving rollback for production.
