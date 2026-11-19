# HelpDesk — production connectivity audit and Railway verification

**Review date:** 2026-11-19
**Repository:** `mdjayedgazi/HelpDesk`
**Branch:** `main`
**Commit under test:** `169f76e645550e97e2f616ac9677018dc174777f` (PR #18 merge)
**Railway project:** `helpdesk-college-demo`, environment `production`, region `ams`
**Services:** `helpdesk-api`, `helpdesk-web`
**Status:** **API and frontend are live and reachable. Redis and PostgreSQL are healthy. Interactive Clerk sign-in and the authenticated dashboard remain unverified because no test credentials exist.**

---

## A. Root causes

### A1. Dashboard failure (fixed this pass) — Railway domain target port did not match the container port

The API deployment had already reached `SUCCESS` and Uvicorn was listening on
`http://0.0.0.0:8080`, but every request to the public API origin timed out with
no HTTP response, or returned `502` at the Railway edge.

| Evidence | Value |
| --- | --- |
| Service domain | `helpdesk-api-production-1dc9dd39.up.railway.app` |
| Domain target port before the fix | **`8000`** |
| Container port from startup log | **`8080`** (`Uvicorn running on http://0.0.0.0:8080`) |
| Source of `8080` | Railway injects `PORT=8080` at runtime; the image default is `PORT=8000` |
| Public `GET /health/live` before the fix | `000` (connection opened, no bytes) / intermittent `502` |
| Deployment status at the same time | `SUCCESS`, container healthy |
| Container-side healthcheck | Passed (Railway's own probe reached the container) |

The API image sets `PORT=8000`, but Railway's runtime `PORT` overrides it to
`8080`. The public domain still targeted `8000`, so the edge had no listener to
route to. The container was healthy, which is why the deployment gate passed and
why this looked like a frontend or database problem rather than routing.

That failure surfaces in the browser exactly as reported: `fetch` rejects
(`ApiError(0)`), and the UI shows **"Could not reach the HelpDesk server. Check
your connection."** The profile request never reaches FastAPI, so
`/api/v1/users/me` never appears in the API logs.

**Fix:** set the API service domain target port to `8080`, matching the running
container. No application code change was required.

### A2. Earlier startup failure (fixed previously) — missing `RATE_LIMIT_REDIS_URL`

The first API deployment (`0964f512-468b-4edd-a5e2-d32be2ad04c2`) crashed during
`Settings._validate_production_configuration()`:

```text
RuntimeError: Invalid production configuration:
RATE_LIMIT_REDIS_URL must be a redis:// or rediss:// URL
```

`ENVIRONMENT=production` + `RATE_LIMIT_ENABLED=true` require a TLS Redis URL.
The variable was absent. A real Upstash `rediss://` database was provisioned,
verified over TLS (`PING`, `SET`, `GET`, `DEL`), and configured through secure
stdin. The API then started and passed `/health/live`.

### A3. Operational risk — the first Redis database was temporary

The first database came from Upstash's no-signup agent endpoint. Those databases
live for three days unless claimed, and the claim/console link was not retained
by the first provisioning script. A **fresh, retry-safe database** was created
with a saved claim link and Railway was switched to it (verified by host hash).
It still expires in three days unless claimed. See section E.

### A4. Configuration observation — Clerk development instance

The frontend build uses `VITE_CLERK_PUBLISHABLE_KEY` starting with `pk_test_`,
i.e. a Clerk **development** instance (`social-ferret-6540.clerk.accounts.dev`).
Clerk works and the FAPI host matches the CSP exactly, but a development
instance is not appropriate for a long-lived production site. This is not the
cause of the dashboard failure.

---

## B. Component status

| Component | Status | Evidence |
| --- | --- | --- |
| Railway API | **PASS** | Deployment `75e9a9df-fe69-4c1e-ac46-4f6e421b3709`, `SUCCESS`, root `/backend`, `backend/Dockerfile`, branch `main`, commit `169f76e` |
| API liveness | **PASS** | `GET /health/live` → `200` `{"status":"ok"}` |
| API readiness | **PASS** | `GET /health/ready` → `200` `{"status":"ready","checks":{"database":"ok","redis":"ok","clamav":"disabled"}}` |
| Neon PostgreSQL | **PASS** | `SELECT 1` → `1`; PostgreSQL `18.7`; pooled host; `sslmode=require`; Alembic `0009_attachment_scan_status` (head) |
| Upstash Redis | **PASS (temporary)** | `rediss://` TLS; direct `PING`/`SET`/`GET`/`DEL` succeeded; readiness reports `redis: ok`; database expires in 3 days unless claimed |
| Clerk authentication | **PARTIAL** | Clerk JS loads, sign-in form renders, no console errors; no interactive sign-in performed (no test credentials) |
| Frontend API URL | **PASS** | `VITE_API_URL=https://helpdesk-api-production-1dc9dd39.up.railway.app`; correct origin, no path; present in the compiled bundle |
| CORS | **PASS** | Preflight `OPTIONS` → `200`, exact origin allowed, credentials on, `Authorization` allowed, rate-limit/request-id headers exposed |
| CSP | **PASS** | API + Clerk FAPI + telemetry + bot-protection origins present; no `unsafe-eval`; no Railway wildcard; no empty substitution |
| Dashboard profile endpoint | **PARTIAL** | `/api/v1/users/me` → `401` without a token (correct, CORS headers present); success path untested without a session |
| User synchronization | **CODE REVIEW OK / UNVERIFIED LIVE** | `get_current_user` links by verified Clerk email or provisions `CUSTOMER`; no live signed-in request available |
| Dashboard UI | **PARTIAL** | `/dashboard` loads `200`; unauthenticated visit redirects to `/sign-in`; signed-in rendering untested |

---

## C. Changes implemented

### Railway configuration (no code change)

| Change | Value |
| --- | --- |
| `RATE_LIMIT_REDIS_URL` on `helpdesk-api` | Replaced with a fresh Upstash `rediss://` URL, set via `railway variable set --stdin` from a mode-`600` temporary file, which was deleted immediately |
| `helpdesk-api` public domain target port | `8000` → `8080` (matches the running container / injected `$PORT`) |
| API deployment | Redeployed from `main` `169f76e` after the changes |

### Documentation

| File | Change |
| --- | --- |
| `data.md` | This review |
| `docs/RAILWAY_COLLEGE_DEMO.md` | Corrected the API port to `$PORT` (observed `8080`) and documented that the service domain target port must match the container port |

### Not changed

- No application code, schema, migration, or test was modified.
- No Railway service, volume, or paid resource was added.
- No database write, migration, reset, or record create/delete was performed.
- Production security settings were preserved (section F).

---

## D. Deployment evidence

| Item | Value |
| --- | --- |
| Deployed commit | `169f76e645550e97e2f616ac9677018dc174777f` |
| API deployment ID | `75e9a9df-fe69-4c1e-ac46-4f6e421b3709` (`SUCCESS`) |
| API deployment root / Dockerfile | `/backend` / `Dockerfile` |
| API healthcheck path | `/health/live`, 300 s timeout |
| API healthcheck result | Passed; container stays running |
| API public origin | `https://helpdesk-api-production-1dc9dd39.up.railway.app` |
| Web deployment ID | `96ac72c1-e946-4f7c-b497-32244124a253` (`SUCCESS`, sleeps when idle) |
| Web deployment root | `/frontend`, commit `169f76e` |
| Web public origin | `https://helpdesk-web-production-d96f8e2b.up.railway.app` |
| CI on merge commit | `CI` run `44090500688` — success |

### D1. Live HTTP results (after the fix)

| Request | Result |
| --- | --- |
| `GET /health/live` | `200` |
| `GET /health/ready` | `200` — database `ok`, redis `ok`, clamav `disabled` |
| `GET /docs` | `404` |
| `GET /redoc` | `404` |
| `GET /openapi.json` | `404` |
| `GET /api/v1/users/me` (no token) | `401` `{"detail":"Invalid or missing Clerk session"}`, `WWW-Authenticate: Bearer` |
| `GET /api/v1/tickets` (no token) | `401` |
| `POST /api/v1/tickets/<id>/attachments` (no token) | `503` (attachments disabled, rejected before auth/upload) |
| `OPTIONS /api/v1/users/me` (frontend origin) | `200`, exact-origin CORS |
| `GET /api/v1/does-not-exist` | `404` |
| Web `/` | `200` |
| Web `/dashboard` | `200` (SPA shell) |
| Web `/sign-in` | `200` |
| Web `/healthz` | `200` |
| Web asset `assets/index-BaVIDY5W.js` | `200` |

### D2. Redis

| Check | Result |
| --- | --- |
| URL scheme | `rediss://` (TLS), host suffix `.upstash.io` |
| Direct connectivity | `PING` true; `SET`/`GET`/`DEL` round-trip true |
| Server | Redis `8.4.0` |
| Railway host match | Host hash `87fbf133d893` matches the newly provisioned database |
| App readiness | `redis: ok` on every `/health/ready` check |
| Secrets | URL never printed, never passed as an argument, never logged; temp file deleted; no `rediss://` string in runtime logs |

### D3. Neon PostgreSQL

Same database as the previous review (local config host hash `e880522f1db4`
equals the Railway config host hash; database `neondb`, role `neon`, pooled
endpoint, `sslmode=require`).

| Check | Result |
| --- | --- |
| `SELECT 1` | `1` |
| Server version | PostgreSQL `18.7` |
| Alembic current | `0009_attachment_scan_status` (head) |
| `users` | **0** |
| `tickets` | `0` |
| `comments` | `0` |
| `attachments` | `0` |
| `users` columns | `id, clerk_id, full_name, username, email, password_hash, role, is_active, created_at, updated_at, image_url` |

The `users` count is `0` now; the 2026-11-17 review recorded `1`. This audit
issued only `SELECT`/`SHOW` statements against PostgreSQL (and one `SET`/`GET`/
`DEL` probe on Redis). The row was not removed by this review. See section E.

### D4. Frontend bundle and CSP

| Check | Result |
| --- | --- |
| Deployed bundle | `assets/index-BaVIDY5W.js`, `1,228,227` bytes |
| API origin in bundle | Present (`2` occurrences) |
| `http://127.0.0.1:8000` | Only in the production-guard branch (`VITE_API_URL is required for a production build`); not reachable in this build and not allowed by CSP |
| `VITE_API_URL` shape | Exact HTTPS origin, no path/query; validated by `apiBase.ts` at build time |
| `VITE_ATTACHMENTS_ENABLED` | `false` |
| Clerk FAPI in CSP | `https://social-ferret-6540.clerk.accounts.dev` |
| Publishable key FAPI match | Yes (decoded key host equals the CSP FAPI host) |
| Clerk telemetry / bot-protection origins | Present |
| `unsafe-eval` | Absent |
| Railway API wildcard | Absent |
| Empty substitutions | None |

Headless Chromium on the live `/sign-in` page:

- `window.Clerk` defined and Clerk script loaded.
- Sign-in form rendered; title `HelpDesk · Support, without the chaos`.
- No console errors, no failed Clerk script loads (only aborted bot-protection
  probes, which are normal challenge traffic).
- One benign CSP violation: `script-src` blocks `Function("")` inside a
  feature-detection helper in the app bundle. The call is wrapped in
  `try/catch` and falls back to `jitless` mode, so it has no functional impact.
- `/dashboard` while signed out redirects to `/sign-in`; no API calls are made
  before authentication, so no spurious "connection" error appears.

---

## E. Remaining problems and required manual actions

| Item | Detail |
| --- | --- |
| **Claim the Upstash database** | The current Redis database is a temporary no-signup database. It expires **3 days after creation** unless claimed. The claim/console link is stored outside the repository at `~/.local/state/helpdesk/upstash-claim.url` (mode `600`, directory `700`). Open it, sign in to Upstash, and click **Claim**; otherwise the API will start failing within three days. |
| **No Owner account** | `users` is empty and `INITIAL_ADMIN_EMAIL` is not set, so no OWNER exists. The first Clerk sign-in provisions a `CUSTOMER` automatically. To get an OWNER, set `INITIAL_ADMIN_EMAIL` and run the one-time bootstrap: `uv run python -m app.commands.bootstrap_owner` from `backend/`. This is a deliberate manual step and was not performed. |
| **Interactive Clerk sign-in** | Not tested: no test credentials and no authorization to create production users. The sign-in page, Clerk script, FAPI origin, and CSP are verified. |
| **Authenticated dashboard** | Not tested for the same reason. The endpoint contract, 401 behavior, CORS, and the auto-provisioning code path were reviewed. |
| **Live rate-limit `429`** | Not triggered. The limiter protects authenticated write endpoints; without a session the request stops at `401`. Redis reachability and startup validation are verified through `/health/ready` and a direct TLS ping. |
| **Clerk instance is `pk_test_`** | Development instance. Functional for a college demo; switch to a production Clerk instance for a durable production deployment. |
| **Cold start** | The container was observed stopping and starting again and served `200` afterwards. A full scheduled sleep→wake cycle was not measured end to end. |
| **`users` table emptied** | Between 2026-11-17 and 2026-11-19 the single row disappeared. Cause not determined; this audit performed no writes. Existing ticket/comment/attachment data was already empty and remains empty. |

---

## F. Production configuration preserved

| Control | State |
| --- | --- |
| `ENVIRONMENT` | `production` |
| `DEPLOYMENT_PROFILE` | `college-demo` |
| `RATE_LIMIT_ENABLED` | `true` |
| `RATE_LIMIT_REDIS_URL` | `rediss://` (TLS) |
| `ATTACHMENTS_ENABLED` | `false` |
| `MALWARE_SCAN_ENABLED` | `false` |
| `AUTO_CREATE_TABLES` | `false` |
| `FRONTEND_URL` | exact Railway web origin |
| CORS | exact origin only; credentials on; no wildcard |
| CSP / security headers | intact on the live frontend |
| Neon PostgreSQL | unchanged, at Alembic head, no writes |
| Clerk auth / role authorization | unchanged; `401` enforced on protected routes |
| Attachments | still rejected (`503`) |
| Service topology | exactly two services; no volume, no paid resource |

No rate-limit bypass, auth bypass, unscanned upload path, development profile,
or wildcard CORS was introduced.

---

## G. Conclusion

The dashboard was not failing because of Neon. It was failing because the public
Railway domain for `helpdesk-api` targeted port `8000` while Railway ran the
container on `8080`. The deployment and container were healthy; only the edge
route was wrong. Aligning the domain target port to `8080` restored the API, and
`/health/ready` now confirms both PostgreSQL and Redis.

The API is live on commit `169f76e` (deployment
`75e9a9df-fe69-4c1e-ac46-4f6e421b3709`), the frontend is live on the same commit,
CORS and CSP are correct, unauthenticated access is rejected with `401`, and
attachments remain disabled. The only unverified link in the chain is a real
Clerk session, which requires credentials this environment does not have.

Two manual follow-ups remain: **claim the Upstash database before it expires**,
and **bootstrap an OWNER** if administrative access is needed.
