# HelpDesk Helm Chart

This directory contains a Helm chart for deploying HelpDesk on Kubernetes.

## Overview

The chart deploys two application components:

| Component | Description | Port |
| --- | --- | --- |
| **Backend** | FastAPI application serving the REST API | 8000 |
| **Frontend** | React/TypeScript SPA served by Nginx | 8080 |

The following services are **external** and must be provisioned separately:

- **PostgreSQL** — primary database
- **Redis** — distributed rate limiting
- **ClamAV** — attachment malware scanning (clamd TCP on port 3310)
- **Clerk** — external authentication service (SaaS)

## Prerequisites

| Tool | Minimum version | Purpose |
| --- | --- | --- |
| Helm | 3.14+ | Chart linting, rendering, install |
| Helmfile | 0.164+ | Declarative release management |
| kubectl | 1.28+ | Cluster interaction |
| Kubernetes cluster | 1.28+ | Runtime |

### Local validation (no cluster required)

```bash
# Lint the chart
helm lint helm/helpdesk

# Render templates to stdout
helm template helpdesk helm/helpdesk

# Validate helmfile syntax
helmfile lint
helmfile -f helmfile.yaml build
```

## 1. Configure image repositories

The chart defaults to placeholder image names. Replace them with your actual
container registry paths:

```yaml
global:
  backendImage:
    repository: ghcr.io/mdjayedgazi/helpdesk-backend
    tag: "v1.0.0"
    pullPolicy: IfNotPresent
  frontendImage:
    repository: ghcr.io/mdjayedgazi/helpdesk-frontend
    tag: "v1.0.0"
    pullPolicy: IfNotPresent
```

If your registry requires authentication, create a Docker-registry secret and
reference it:

```bash
kubectl create secret docker-registry my-registry-secret \
  --docker-server=ghcr.io \
  --docker-username=USERNAME \
  --docker-password=TOKEN \
  -n helpdesk
```

Then set `global.imagePullSecrets`:

```yaml
global:
  imagePullSecrets:
    - name: my-registry-secret
```

## 2. Provide secrets securely

**Never commit secrets to the repository.** Create a Kubernetes Secret and
reference it via `backend.existingSecret`:

```bash
kubectl create secret generic helpdesk-secrets \
  --from-literal=DATABASE_URL="postgresql+psycopg://user:pass@postgres:5432/helpdesk" \
  --from-literal=CLERK_SECRET_KEY="sk_live_..." \
  --from-literal=RATE_LIMIT_REDIS_URL="redis://redis:6379" \
  --from-literal=CLAMAV_HOST="clamav.default.svc.cluster.local" \
  --from-literal=RATE_LIMIT_TRUSTED_PROXIES="10.0.0.0/8" \
  --from-literal=FRONTEND_URL="https://helpdesk.example.com" \
  -n helpdesk
```

Then in your values:

```yaml
backend:
  existingSecret: helpdesk-secrets
```

The chart will **fail with a clear error** if `backend.existingSecret` is empty
and `ENVIRONMENT` is set to `production`.

### Required secret keys

| Key | Description |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string (psycopg async driver) |
| `CLERK_SECRET_KEY` | Clerk production secret key (`sk_live_...`) |
| `RATE_LIMIT_REDIS_URL` | Redis connection URL |
| `CLAMAV_HOST` | ClamAV clamd hostname |
| `RATE_LIMIT_TRUSTED_PROXIES` | Trusted reverse-proxy CIDRs |
| `FRONTEND_URL` | Public frontend HTTPS origin |

## 3. Configure external services

### Database

The backend connects to PostgreSQL via `DATABASE_URL` in the Kubernetes Secret.
The database is **not** bundled in the chart — deploy it separately (e.g.,
Cloud SQL, RDS, or a PostgreSQL operator).

### Redis

Rate limiting requires a shared Redis instance. Provide the URL via
`RATE_LIMIT_REDIS_URL` in the secret.

### ClamAV

Attachment scanning requires a ClamAV daemon reachable at `CLAMAV_HOST:CLAMAV_PORT`.
Deploy a ClamAV service in the cluster or point to an external instance.

### Frontend URL

Set `FRONTEND_URL` in the secret to the public HTTPS origin of the frontend.
This is used for CORS and Clerk's authorized-party check.

## 4. Persistent uploads

The backend stores uploaded attachments on a filesystem at `/data/uploads`.
The chart creates a PersistentVolumeClaim by default:

```yaml
backend:
  persistence:
    enabled: true
    mountPath: /data/uploads
    accessModes:
      - ReadWriteOnce
    size: 10Gi
```

**Important:** `ReadWriteOnce` means only one pod can mount the volume. The
default `backend.replicaCount` is `1`. To scale beyond 1 replica, migrate to
shared storage (NFS, CSI driver) or object storage (S3-compatible).

## 5. Configure Ingress and TLS

Ingress is disabled by default. To enable it:

```yaml
ingress:
  enabled: true
  className: "nginx"
  hosts:
    - host: helpdesk.example.com
      paths:
        - path: /
          pathType: Prefix
  tls:
    - secretName: helpdesk-tls
      hosts:
        - helpdesk.example.com
```

Create the TLS secret separately (e.g., via cert-manager or manual creation):

```bash
kubectl create secret tls helpdesk-tls \
  --cert=tls.crt --key=tls.key -n helpdesk
```

## 6. Run migrations safely

Database migrations are **not** included as a Helm hook. Run them manually
before or during deployment:

```bash
# Option 1: Run migration in a temporary pod
kubectl run helpdesk-migrate \
  --image=ghcr.io/mdjayedgazi/helpdesk-backend:v1.0.0 \
  --restart=Never \
  --env-from=secret/helpdesk-secrets \
  --env="ENVIRONMENT=production" \
  --command -- alembic upgrade head \
  -n helpdesk

# Wait for completion
kubectl wait --for=condition=completed pod/helpdesk-migrate -n helpdesk
kubectl delete pod helpdesk-migrate -n helpdesk
```

Take a database backup before running migrations.

## 7. Lint and render the chart

```bash
# Lint
helm lint helm/helpdesk

# Lint with custom values
helm lint helm/helpdesk -f my-values.yaml

# Render templates (dry-run, no cluster changes)
helm template helpdesk helm/helpdesk

# Render with custom values
helm template helpdesk helm/helpdesk -f my-values.yaml
```

## 8. Preview changes before applying

```bash
# Helm preview
helm diff upgrade helpdesk helm/helpdesk --install

# Helmfile preview
helmfile -f helmfile.yaml diff
```

## 9. Install or upgrade the release

```bash
# Using Helm directly
helm upgrade --install helpdesk helm/helpdesk \
  -n helpdesk \
  --create-namespace \
  -f my-values.yaml

# Using Helmfile
helmfile -f helmfile.yaml apply
```

## 10. Inspect health, logs, and status

```bash
# Release status
helm status helpdesk -n helpdesk

# Pod status
kubectl get pods -n helpdesk -l app.kubernetes.io/instance=helpdesk

# Logs
kubectl logs -n helpdesk -l app.kubernetes.io/component=backend --tail=100
kubectl logs -n helpdesk -l app.kubernetes.io/component=frontend --tail=100

# Describe a failing pod
kubectl describe pod <pod-name> -n helpdesk

# Check readiness
kubectl exec -n helpdesk deploy/helpdesk-backend -- \
  wget -q -O- http://127.0.0.1:8000/health/ready
```

## 11. Roll back a release

```bash
# View release history
helm history helpdesk -n helpdesk

# Roll back to previous revision
helm rollback helpdesk <REVISION> -n helpdesk
```

## 12. Uninstall

```bash
helm uninstall helpdesk -n helpdesk
```

**Warning:** This removes deployments, services, and ConfigMaps, but **does not**
delete the PersistentVolumeClaim or the database. To also remove the PVC:

```bash
kubectl delete pvc helpdesk-helpdesk-uploads -n helpdesk
```

**Do not delete the PVC or database unless you have verified backups.**

## Known limitations

1. **Single backend replica by default** — The backend stores attachments on a
   local filesystem. Multi-replica deployment requires shared storage or
   migration to object storage (S3-compatible).

2. **No bundled database** — PostgreSQL, Redis, and ClamAV must be provisioned
   externally. The chart does not include subcharts for these dependencies.

3. **Frontend build-time variables** — `VITE_API_URL` and
   `VITE_CLERK_PUBLISHABLE_KEY` are baked into the JavaScript bundle at build
   time. They must be provided as build arguments when building the frontend
   image, not as runtime environment variables.

4. **Migrations are manual** — The chart does not run Alembic migrations
   automatically. Run them as a separate step before or during deployment.

## Values reference

See [`values.yaml`](./values.yaml) for the complete list of configurable values
with documentation comments.
