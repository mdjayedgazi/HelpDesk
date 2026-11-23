# Monitoring and alerting

This document defines the production monitoring plan for HelpDesk. It states
what the application exposes, what must be configured in the platform (Railway,
Neon, Upstash) or an external monitor, and the response expected for each alert.

> **Honest status.** The repository exposes the signals below. **No alerting
> integration is configured by this repository, and none is claimed to be
> configured.** Alerts must be wired up in the platforms and an external uptime
> monitor by the account owner. Anything marked **EXTERNAL** requires dashboard
> access and is not verified here.

## 1. Signals the application already exposes

| Signal | Where | Good value | Notes |
| --- | --- | --- | --- |
| Liveness | `GET /health/live` | `200 {"status":"ok"}` | Process only; never touches dependencies. |
| Readiness | `GET /health/ready` | `200 {"status":"ready",...}` | Checks `database`, `schema`, `redis`, `clamav`. |
| Readiness detail | fields of `/health/ready` | `database: ok`, `schema: ok`, `redis: ok` (or `disabled`), `clamav: disabled`/`ok` | Coarse categories only — no hostnames, URLs, or exception text. |
| Structured logs | stdout (Railway log stream) | JSON (`LOG_JSON=true`) | Bearer tokens, `sk_*` keys, and credential-bearing URLs are redacted before logging. |
| Request correlation | `X-Request-ID` response header + log field | present | Echoes a client-supplied safe id or generates one. |
| Rate-limit headers | `X-RateLimit-*` on protected writes | present | Useful to confirm the limiter is live. |

Readiness is the **required** uptime endpoint. It fails (503) when the database
or schema is wrong in production, or when Redis/ClamAV is enabled and unreachable.

Importantly, readiness does **not** leak secrets: it never returns connection
strings, hosts, ports, credentials, or exception messages. Alerts built on it are
therefore safe to route to a general channel.

## 2. Alert catalogue

Thresholds are starting suggestions, not laws; tune them to real traffic. All
"page" alerts should reach an on-call human; "ticket" alerts can be async.

| # | Alert | Source | Suggested threshold | Severity | Response |
| --- | --- | --- | --- | --- | --- |
| A1 | API readiness failing | External uptime probe on `GET https://<api>/health/ready` | Non-200 for 2 consecutive checks (≈2 min) | **Page** | Open `/health/ready` body; identify the failing category (`database`/`schema`/`redis`/`clamav`). See runbook §4. |
| A2 | API liveness failing | External probe on `/health/live` | Non-200 for 2 checks | **Page** | Process down/crashed. Check Railway deployment + logs; roll back if a new deploy caused it. |
| A3 | Elevated 5xx rate | Railway logs / log drain / provider | > 2% of requests over 5 min | **Page** if sustained | Inspect logs by `X-Request-ID`; check downstream dependencies first. |
| A4 | Elevated latency | Provider / synthetic probe | p95 > 2 s over 10 min | Warn | Check DB latency, pool saturation, Redis timeouts, Clerk API latency. |
| A5 | Database connection failures | Neon Monitoring / app logs | Any sustained connection errors | **Page** | Check Neon status, connection limit, `DB_POOL_SIZE`/`DB_MAX_OVERFLOW`. |
| A6 | DB pool saturation | Neon connections vs `DB_POOL_SIZE + DB_MAX_OVERFLOW` | ≥ 80% of the per-replica cap | Warn | Reduce pool size, add pooling, or investigate slow queries (`DB_STATEMENT_TIMEOUT_MS`). |
| A7 | Schema drift / migration mismatch | `/health/ready` `schema` category | `schema != ok` | **Page** | The running image expects a different Alembic head. Verify `alembic current`; redeploy or roll forward. |
| A8 | Redis unavailable | `/health/ready` `redis` category; protected-endpoint 503s | `redis: error` or bursts of 503 | **Page** | Rate limiting is **fail-closed**: protected writes return 503. Restore Upstash availability. |
| A9 | Attachment scanner unavailable | `/health/ready` `clamav` category | `clamav: error` | Warn (page if uploads are business-critical) | Uploads return 503 (fail-closed). Restore clamd; run the legacy rescan only after it is healthy. |
| A10 | Deployment failure | Railway deployment events / GitHub Actions | Any failed deploy or failed pre-deploy migration | **Page** | Deployment should not become active. Check CI, migration logs; fix forward. |
| A11 | Frontend availability | External probe on `GET https://<web>/healthz` | Non-200 for 2 checks | **Page** | Check Railway web service status and the last deploy. |
| A12 | Backup/PITR disabled | Neon Settings → Backups | PITR off or backups off | **Page** | Enable a plan with PITR / scheduled backups before continuing (see `DATABASE_BACKUP_RESTORE.md`). |

## 3. What each platform provides

### Railway (EXTERNAL)
- Deployment status and history per service (`railway status`, dashboard).
- Health-check-driven restarts (the service healthcheck path).
- Log stream (JSON) — route to a log drain if you need retention/search.
- **Not configured by this repo:** alert routing. Configure Railway notifications
  or a log-drain-based alert in the dashboard.

### Neon (EXTERNAL)
- Project **Monitoring → Connections / Compute / Storage**.
- **Settings → Backups** for PITR status and retention.
- **Not configured by this repo:** alert rules. Add connection/storage/backup
  alerts in the Neon console.

### Upstash (EXTERNAL)
- Database status, memory, eviction, and request metrics in the console.
- **Not configured by this repo:** alerting. Add memory/availability alerts.

### External uptime monitor (RECOMMENDED, EXTERNAL)
Use any HTTPS prober (for example a managed uptime service) on:
- `https://<api-host>/health/ready` (A1)
- `https://<web-host>/healthz` (A11)

Point the alerts at the on-call channel. These probes only read public,
non-sensitive endpoints.

### Error tracking (OPTIONAL, EXTERNAL)
If you add an error tracker, feed it the backend JSON logs (which are already
redacted) or instrument the app. Do **not** send request bodies, authorization
headers, or database URLs. This repository does not include an error-tracking SDK.

## 4. Response procedures (summary)

1. **A1/A5/A6/A7 (database/schema):** read `/health/ready`; if `schema != ok`,
   never "fix" it by pointing at the wrong database — verify `alembic current`
   against the intended head and redeploy the matching image. If connectivity,
   check Neon status and the connection limit before changing pool sizes.
2. **A8 (Redis):** rate limiting is fail-closed, so protected writes return 503
   by design. Do not disable rate limiting to "restore" traffic in production
   without a deliberate decision; restore Upstash instead.
3. **A9 (ClamAV):** uploads fail closed. Do not set `MALWARE_SCAN_ENABLED=false`
   in production to bypass it; restore clamd.
4. **A10/A2 (deploy/process):** prefer rolling back to the previous known-good
   image over patching live. Never run destructive migrations to roll back; use
   a forward fix (see `DEPLOYMENT.md §3`).
5. **A12 (backups):** treat missing backups as a release blocker; see the restore
   runbook.

## 5. Ownership

Record outside this repository: the on-call owner, the alert destination channel,
and the escalation path. Monitoring without an owner is not monitoring.

## 6. What is intentionally NOT exposed

- No `/metrics` Prometheus endpoint is shipped (no dependency on a specific
  scraping stack). If you add one, keep it unauthenticated-but-internal or behind
  the private network, and never include secrets or PII in labels.
- Health responses stay coarse to avoid information disclosure to anonymous
  callers.
