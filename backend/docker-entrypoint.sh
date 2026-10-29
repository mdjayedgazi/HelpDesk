#!/bin/sh
set -eu

# Railway mounts a volume owned by root. Prepare the upload directory while we
# still have root, then run the application (and Alembic pre-deploy commands) as
# the unprivileged app user.
UPLOAD_DIR="${UPLOAD_DIR:-/data/uploads}"

if [ "$(id -u)" = "0" ]; then
    mkdir -p "$UPLOAD_DIR"
    chown -R app:app "$UPLOAD_DIR"
    exec gosu app "$@"
fi

exec "$@"
