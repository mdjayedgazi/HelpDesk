# Production image for the FastAPI backend.
#
# Railway builds this file when the service root is `backend/`. The process
# runs as an unprivileged user; the entrypoint only uses root to create/chown the
# mounted upload volume before dropping privileges with gosu.
FROM ghcr.io/astral-sh/uv:0.11.27 AS uv

FROM python:3.13.1-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH" \
    PORT=8000 \
    UPLOAD_DIR=/data/uploads

RUN apt-get update \
    && apt-get upgrade -y \
    && apt-get install --no-install-recommends -y gosu \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data/uploads \
    && chown -R app:app /data

# The runtime does not use the system pip: dependencies live in the uv-built
# venv at /app/.venv. The base image's bundled pip ships a stale setuptools
# wheel whose metadata image scanners flag, even though it is never imported at
# runtime. Upgrade pip during the build (so any build-time use is patched), then
# remove the system pip + setuptools from the final image entirely — they are
# dead weight here — which also removes the false-positive finding.
RUN python -m pip install --no-cache-dir --upgrade pip setuptools \
    && python -m pip uninstall -y pip setuptools

WORKDIR /app

COPY --from=uv /uv /uvx /usr/local/bin/
COPY --chown=app:app pyproject.toml uv.lock .python-version README.md ./
# Install without leaving the uv download/unpack cache in the runtime image. The
# cache (~130 MB) is not needed at runtime and can carry stale build-time wheels
# (e.g. an older setuptools) that image scanners flag as vulnerable even though
# the application never imports them. UV_NO_CACHE keeps the final image clean.
RUN UV_NO_CACHE=1 uv sync --frozen --no-dev --no-install-project \
    && rm -rf /root/.cache/uv \
    && rm -f /usr/local/bin/uv /usr/local/bin/uvx

COPY --chown=app:app . .
COPY --chmod=0755 docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT', '8000') + '/health/live', timeout=3)"

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port \"${PORT:-8000}\" --proxy-headers --forwarded-allow-ips \"${FORWARDED_ALLOW_IPS:-127.0.0.1}\""]
