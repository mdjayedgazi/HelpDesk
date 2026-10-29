# HelpDesk production deployment (Railway)

This runbook describes the production topology, the Railway dashboard work, and
the smoke tests for the backend and frontend in this repository. It does not
contain real credentials and it does not claim that a Railway deployment has
already been performed.

## Verification boundary

**Verified locally in this remediation pass**

- `backend/Dockerfile` builds and the container starts, serves
  `/health/live`, returns `503` from `/health/ready` when a dependency is down,
  and returns `404` for `/docs` with `ENVIRONMENT=production`.
- `frontend/Dockerfile` builds with the required `VITE_*` build arguments, runs
  Nginx on port `8080`, serves the SPA fallback, emits the configured CSP and
  cache headers, and returns `404` for a missing asset.
- Backend tests, frontend typecheck/lint/tests/build, disposable PostgreSQL and
  Redis suites, and Docker smoke tests are recorded in `data.md`.

**Requires Railway account access and remains `NOT VERIFIED`**

- Service creation, variables, volume attachment, private networking, domains,
  TLS certificates, deployment health, backups/PITR, monitoring, and alerting.
- A deployed ClamAV service and the one-time rescan of legacy attachments.
- A deployed Redis instance and production smoke tests against the real
  hostnames.

Do not enable HSTS, announce the domain, or treat the deployment as live until
the dashboard checks and smoke tests below have been completed.

## Topology

| Railway service | Source root | Image/port | Persistent state |
| --- | --- | --- | --- |
| `helpdesk-api` | `backend/` | `backend/Dockerfile`, port `8000` (honours `PORT`) | volume mounted at `/data`; uploads at `/data/uploads` |
| `helpdesk-web` | `frontend/` | `frontend/Dockerfile`, port `8080` | none |
| `helpdesk-postgres` | Railway PostgreSQL | private TCP `5432` | managed database |
| `helpdesk-redis` | Railway Redis | private TCP `6379` | rate-limit counters |
| `helpdesk-clamav` | ClamAV/clamd image or managed scanner | private TCP `3310` | virus signatures (if self-hosted) |

The backend and frontend are separate services. The frontend never proxies API
requests: its JavaScript bundle calls the public backend origin directly.

Railway config-as-code (`railway.toml` / `railway.json`) is not used in this
repository. Configure the services and variables in the Railway dashboard.

## 1. Backend service

1. Create a service from this repository and set its **root directory** to
   `backend/`. Railway will detect `backend/Dockerfile`.
2. Keep the Docker command/entrypoint defaults. The image runs Uvicorn on
   `$PORT` and the entrypoint prepares the mounted upload volume before
   dropping to the unprivileged `app` user (uid `10001`).
3. Attach a volume to the service at `/data`. Set `UPLOAD_DIR=/data/uploads`.
   Do not point uploads at a container-local directory: they disappear on the
   next deployment.
4. Configure these service variables:

| Variable | Production value / guidance |
| --- | --- |
| `ENVIRONMENT` | `production` |
| `DATABASE_URL` | Railway PostgreSQL reference. `postgresql://...` is normalised to the psycopg async driver. It must be a non-local PostgreSQL host. |
| `CLERK_SECRET_KEY` | Clerk **production** secret, starting with `sk_live_`. Never put this in the frontend. |
| `FRONTEND_URL` | Exact HTTPS frontend origin, for example `https://helpdesk.acme-corp.com`. No path, query, or fragment. |
| `CORS_ORIGINS` | Leave empty in production. Additional exact HTTPS origins only if a second first-party frontend exists. |
| `AUTO_CREATE_TABLES` | `false` |
| `DATABASE_ECHO` | `false` |
| `UPLOAD_DIR` | `/data/uploads` |
| `MALWARE_SCAN_ENABLED` | `true` |
| `CLAMAV_HOST` | Private hostname of the ClamAV service, for example `helpdesk-clamav.railway.internal`. Not `localhost`. |
| `CLAMAV_PORT` | `3310` (or the port exposed by the scanner service) |
| `RATE_LIMIT_ENABLED` | `true` |
| `RATE_LIMIT_REDIS_URL` | Railway Redis private URL (`redis://...` or `rediss://...`), not localhost. |
| `RATE_LIMIT_TRUSTED_PROXIES` | Non-empty list of the direct reverse-proxy/edge CIDRs that are allowed to supply `X-Forwarded-For`. Use the actual Railway edge ranges observed for the service. `0.0.0.0/0,::/0` is acceptable only when the service has no network path except Railway's edge; blank is rejected. |
| `HSTS_ENABLED` | `false` until the API custom domain has a verified TLS certificate and the smoke tests pass; then `true`. |
| `HSTS_MAX_AGE_SECONDS` | `31536000` after TLS verification. |
| `LOG_LEVEL` | `INFO` |
| `LOG_JSON` | `true` |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | Start with `5` / `10`; size against the PostgreSQL connection limit and number of API instances. |
| `DB_CONNECT_TIMEOUT_SECONDS` | `10` |
| `DB_STATEMENT_TIMEOUT_MS` | `30000` |
| `MAX_UPLOAD_BYTES` | `5242880` unless a reviewed product limit says otherwise. |
| `MAX_ATTACHMENTS_PER_TICKET` | `20` |
| `MAX_TICKET_ATTACHMENT_BYTES` | `52428800` |

The application refuses to start in production if a required value is missing,
a placeholder/localhost value is present, Clerk is not a production key, rate
limiting or scanning is disabled, the upload path is not durable, or the
database/Redis settings are invalid. The startup error names the variables but
never echoes secret values.

5. Set the **pre-deploy command** to:

   ```bash
   alembic upgrade head
   ```

   Take a database backup first. This command is suitable for normal forward
   migrations. Never use `AUTO_CREATE_TABLES=true` in production.

6. Set the **health check path** to `/health/ready` and allow enough startup
   time for Redis, PostgreSQL, and ClamAV to become reachable. Use
   `/health/live` only for process-liveness checks; it does not prove that
   dependencies are available. The image also has a local liveness
   `HEALTHCHECK` against `/health/live`.

7. Expose the service over HTTPS through a Railway domain or a custom domain.
   Keep the private service hostname private; the frontend uses the public API
   origin.

### Attachment rescan after migration 0009

Migration `0009_attachment_scan_status` marks all pre-existing attachments
`PENDING`, so they are not downloadable. After ClamAV is reachable and the
backend is running with the volume mounted, run the one-off command with the
same `DATABASE_URL`, `UPLOAD_DIR`, `MALWARE_SCAN_ENABLED`, and `CLAMAV_*`
environment:

```bash
python -m app.commands.scan_attachments
```

The command promotes clean files, deletes infected bytes, leaves scanner
failures `PENDING`, and exits non-zero if the scanner is unavailable. A one-off
Railway shell/job must mount the same `/data` volume as the API service; a job
without the volume cannot see the files.

## 2. Frontend service

1. Create a service from this repository and set its **root directory** to
   `frontend/`. Railway will detect `frontend/Dockerfile`.
2. Set these **build-time** service variables. Railway passes defined variables
   to matching Dockerfile `ARG` declarations, which this Dockerfile uses:

   | Variable | Value |
   | --- | --- |
   | `VITE_API_URL` | Exact public backend HTTPS origin, for example `https://api.acme-corp.com` |
   | `VITE_CLERK_PUBLISHABLE_KEY` | Clerk production publishable key (`pk_live_...`) |

   `VITE_API_URL` is intentionally required and validated at build time. The
   build fails for a missing, HTTP, localhost, path-bearing, or otherwise
   non-origin value. These values are baked into the JavaScript bundle, so a
   change requires a redeploy, not just a container restart.

3. Set these **runtime** container variables:

   | Variable | Value |
   | --- | --- |
   | `API_ORIGIN` | The same exact HTTPS backend origin used for `VITE_API_URL`; used in the CSP `connect-src`. |
   | `CLERK_FAPI_ORIGIN` | Optional Clerk Frontend API origin for a custom Clerk domain. Leave unset for the default Clerk development hosts; set an exact HTTPS origin for production custom domains. |
   | `HSTS_ENABLED` | `false` until the frontend custom domain has verified TLS and the smoke tests pass. |
   | `HSTS_MAX_AGE_SECONDS` | `31536000` after TLS verification. |

   The container refuses to start if `API_ORIGIN` is missing, not HTTPS, or
   contains a path/query/fragment or shell-injection characters.

4. Railway should route the service to container port `8080`. The Nginx
   configuration provides:

   - SPA fallback (`/dashboard`, ticket routes, etc. return `index.html`);
   - `404` for missing `/assets/*` files instead of returning the SPA shell;
   - long-lived immutable caching for fingerprinted `/assets/*` and
     `Cache-Control: no-cache` for the shell;
   - a Clerk-compatible CSP, `X-Content-Type-Options`, `X-Frame-Options`,
     `Referrer-Policy`, `Permissions-Policy`, and optional HSTS;
   - `/healthz` for Railway health checks.

5. Add the public frontend domain and backend API domain to Clerk's allowed
   origins/redirect URLs in the Clerk dashboard. This is external to this
   repository and remains a dashboard task.

### Horizontal scaling limitation

Uploads are stored on a Railway volume attached to one backend service.
Running multiple backend replicas without shared storage (for example an
object store) will make attachments appear on only some replicas. Keep one
backend replica for the current design, or migrate attachment storage before
scaling out. Redis is shared and is not a substitute for file storage.

## 3. PostgreSQL

- Use Railway PostgreSQL in the same project/private network.
- Confirm the database plan includes the backup/PITR retention required by the
  product. Take a manual backup before the first migration and before applying
  `0008_ticket_number_not_null` (it takes an `ACCESS EXCLUSIVE` lock while
  backfilling NULL ticket numbers).
- Verify a restore into a disposable database, not only that a backup exists.
- Apply migrations in staging first, then production, with the matching
  application release.
- Keep `AUTO_CREATE_TABLES=false`; the schema is owned by Alembic.

Useful checks from a one-off backend shell:

```bash
alembic current
alembic history --verbose
alembic upgrade head
alembic check
```

Do **not** routinely downgrade a production database. `0001` drops all tables;
migrations are not a data-preserving rollback. Prefer a forward fix and an
application rollback.

## 4. Redis

- Create Railway Redis in the same project/private network.
- Set `RATE_LIMIT_REDIS_URL` to its private URL and `RATE_LIMIT_ENABLED=true`.
- The limiter uses short-lived keys. Losing Redis resets rate-limit counters but
  does not lose application data; when Redis is unreachable, protected
  endpoints fail closed with `503` and startup/readiness report the failure.
- Do not expose Redis publicly and do not substitute an in-process counter for
  multiple workers.

## 5. ClamAV

- Deploy a clamd service in the same Railway project/private network. The
  official ClamAV image or a managed clamd endpoint is acceptable; it must speak
  the INSTREAM TCP protocol on a private port such as `3310`.
- Do not expose clamd to the public internet.
- Allow time for the first signature database download. `/health/ready` will
  return `503` with `clamav: error` until the scanner accepts TCP connections.
- Set `MALWARE_SCAN_ENABLED=true` and `CLAMAV_HOST`/`CLAMAV_PORT` on the API
  service. Uploads are fail-closed: scanner errors return `503`, infected files
  return `422`, and only an explicit `CLEAN` result is published.
- Run the legacy rescan described above. Keep the signature database and
  scanner healthy; a stale scanner is still a dependency failure.

## 6. TLS, domains, CSP, and HSTS

1. Add the public frontend and API domains in Railway and wait for certificates
   to be issued and verified.
2. Set `FRONTEND_URL` and `CORS_ORIGINS` to the final HTTPS origins; set
   `VITE_API_URL` and `API_ORIGIN` to the final HTTPS API origin. Rebuild the
   frontend after changing `VITE_*`.
3. Test both domains over HTTPS (not just the Railway-generated hostname) and
   test Clerk sign-in/redirects.
4. Only then set `HSTS_ENABLED=true` on both services. HSTS is intentionally
   opt-in: enabling it on an HTTP-only or misconfigured origin can lock clients
   out. `includeSubDomains` is emitted; do not enable it if any subdomain is not
   HTTPS.
5. Keep the API documentation routes disabled in production. `/docs`,
   `/redoc`, and `/openapi.json` should return `404`.
6. Keep the backend CSP strict. Swagger/ReDoc receive a separate
   development-only policy; production API responses use `default-src 'none'`.

## 7. Monitoring and operations

Configure, and record evidence for, at least:

- Railway health checks against `/health/ready` (API) and `/healthz` (web).
- Alerts for elevated 5xx, readiness failures, Redis failures, ClamAV failures,
  database connection exhaustion, and deployment failures.
- Log retention. Production JSON logs redact bearer tokens, Clerk keys,
  credential-bearing database/Redis URLs, and common password/secret fields;
  request bodies and authorization headers are not logged.
- Backup/PITR verification and a restore drill.
- A spend limit and resource alerts so a runaway client cannot exhaust the
  database, Redis, or scanner.
- A rollback procedure: redeploy the previous known-good image, then use a
  forward migration fix if the previous image is incompatible with the current
  schema.

## 8. Post-deployment smoke tests

Run these against the real hostnames after the deployment is healthy. Do not
paste secrets into shell history or CI logs.

```bash
API=https://api.acme-corp.com
WEB=https://helpdesk.acme-corp.com

# Liveness and dependency readiness
curl -fsS "$API/health/live"
curl -fsS "$API/health/ready"

# Production documentation must not be exposed
test "$(curl -sS -o /dev/null -w '%{http_code}' "$API/docs")" = 404
test "$(curl -sS -o /dev/null -w '%{http_code}' "$API/openapi.json")" = 404

# Security headers and no-store on an API response
curl -sS -D - -o /dev/null "$API/api/v1/users/me" | \
  grep -Ei '^(HTTP/|x-content-type-options|x-frame-options|referrer-policy|permissions-policy|content-security-policy|cache-control|x-request-id):'

# SPA shell and fallback
test "$(curl -sS -o /dev/null -w '%{http_code}' "$WEB/")" = 200
test "$(curl -sS -o /dev/null -w '%{http_code}' "$WEB/dashboard")" = 200

# A missing fingerprinted asset must not fall back to index.html
test "$(curl -sS -o /dev/null -w '%{http_code}' "$WEB/assets/missing.js")" = 404

# After any write, verify the expected 413/422/429 responses with a disposable
# account; do not use customer data for load or abuse testing.
```

Then complete an end-to-end Clerk sign-in on the real frontend domain, open a
ticket, upload a benign file, download it, and verify the scan result in the UI.
Repeat with a known EICAR test file only in a disposable QA environment.

## 9. Dashboard checklist

Mark each item verified only after observing it in Railway or the external
provider. These are not satisfied by local Docker builds.

- [ ] Backend service root `backend/`, Dockerfile detected, deployment healthy.
- [ ] Frontend service root `frontend/`, Dockerfile detected, deployment healthy.
- [ ] PostgreSQL attached; `DATABASE_URL` uses the private service.
- [ ] Redis attached; `RATE_LIMIT_REDIS_URL` uses the private service.
- [ ] ClamAV deployed privately; `CLAMAV_HOST` reachable on port `3310`.
- [ ] Backend volume mounted at `/data`; `UPLOAD_DIR=/data/uploads`.
- [ ] Backend pre-deploy command `alembic upgrade head` succeeds.
- [ ] `alembic current` matches the expected head; `alembic check` is clean.
- [ ] Legacy `PENDING` attachments rescanned with
      `python -m app.commands.scan_attachments`.
- [ ] Frontend build-time `VITE_API_URL` and `VITE_CLERK_PUBLISHABLE_KEY` set.
- [ ] Frontend runtime `API_ORIGIN` matches `VITE_API_URL`.
- [ ] API and web custom domains have verified TLS certificates.
- [ ] Clerk production keys and allowed origins/redirects configured.
- [ ] HSTS enabled only after TLS and smoke-test verification.
- [ ] PostgreSQL backups/PITR enabled and a restore was tested.
- [ ] Monitoring/alerts and log retention configured.
- [ ] `/health/live` and `/health/ready` return `200` in production.
- [ ] `/docs`, `/redoc`, and `/openapi.json` return `404`.
- [ ] API security headers and `Cache-Control: no-store` observed.
- [ ] SPA fallback, asset caching, and missing-asset `404` observed.
- [ ] End-to-end sign-in, ticket creation, upload, scan, download tested.
- [ ] Worker/replica count is `1` for the current volume-backed upload design.

## 10. Known constraints

- The repository contains no deployment credentials, Railway project IDs, or
  production secrets.
- No commit, push, merge, or Railway deployment was performed as part of the
  remediation. The working tree is intentionally uncommitted.
- The backend does not use WebSockets, background workers, or an object store.
  Uploads and the scanner are synchronous and fail closed.
- The frontend production bundle is large (about 1.23 MB JS, 342 KB gzip in the
  verified build). It works, but code-splitting is a future performance task.
- Five moderate advisories remain in the frontend **development** toolchain
  (`vitest` / `@vitest/ui` dependencies); production `npm audit --omit=dev`
  reports zero vulnerabilities. See `data.md`.
