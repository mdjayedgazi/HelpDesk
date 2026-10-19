# HelpDesk backend

FastAPI + SQLModel (async SQLAlchemy, PostgreSQL via psycopg v3) with Clerk
authentication.

## Setup

1. Create `backend/.env` from `.env.example` and fill in `CLERK_SECRET_KEY`
   and `DATABASE_URL`.
2. Install dependencies (the project uses [uv](https://docs.astral.sh/uv/)):

   ```bash
   uv sync
   ```

3. Apply database migrations:

   ```bash
   alembic upgrade head
   ```

   See [`migrations/README.md`](migrations/README.md) for the full migration
   workflow, including how to adopt an existing database.

   `AUTO_CREATE_TABLES` is disabled by default. It exists only as a local
   development convenience and must stay off in production: the schema is
   owned by Alembic.

## Run

```bash
uv run fastapi dev app/main.py
```

## Tests

```bash
uv run pytest -q
```

The tests run against an in-memory SQLite database with Clerk stubbed out, so
they need no external services.
