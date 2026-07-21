# Deployment Foundations

This repository now includes container and CI foundations for AW Center. The files are intentionally conservative: secrets, certificates, SQLite databases, media uploads, generated static files, and dependency folders are excluded from images and source control.

## Container images

- `backend/Dockerfile` builds Vite assets in an isolated Node stage, copies the immutable result to `/app/frontend-dist`, collects WhiteNoise assets, verifies Django SPA/static responses, and runs `awcenter.wsgi` with Gunicorn.
- `frontend/Dockerfile` remains an optional standalone Vite/Nginx image for a future CDN or split-static topology; the default Compose topology does not require it.
- `.dockerignore` excludes local runtime artifacts and secrets from Docker build contexts.

## Local orchestration

Use Docker Compose from the repository root:

```bash
docker compose up --build
```

Services:

| Service | Purpose | Local port |
|---|---|---|
| `backend` | Same-origin Django API, SPA shell, and WhiteNoise assets | `8080` |
| `worker` | Durable job executor and lease heartbeat | internal |
| `database` | PostgreSQL production-grade database candidate | `5432` |
| `redis` | Cache backend candidate | internal |

The Django settings default to SQLite for local runs and switch through `DATABASE_URL` for production or Compose. PostgreSQL is the recommended production database. Redis can be enabled with `CACHE_URL`.

## Required backend environment variables

These variables are read by `backend/awcenter/settings.py`.

| Variable | Required | Default | Notes |
|---|---:|---|---|
| `SECRET_KEY` | Production yes | Development fallback only when `DEBUG=True` | Keep external and rotate through the deployment secret manager. |
| `DEBUG` | No | `False` | Must be `False` in production. |
| `IPV4_ADDRESS` | Yes | None | Used in allowed hosts and reset URL defaults. |
| `PORT` | Yes | None | Used in reset URL defaults and server binding helpers. |
| `DOCPROOF_URL` | Yes | None | DocProof integration base URL. |
| `DOORS_EXECUTABLE` | Yes | None | External DOORS executable path. |
| `DOORS_DATABASE` | No | Empty | Optional DOORS `port@host` database selection. |
| `DOORS_AUTO_START_CLIENT` | No | `False` | Keep disabled unless desktop process startup is explicitly required. |
| `DOORS_MAX_RESULT_BYTES` | No | `10485760` | Maximum DXL result-file bytes. |
| `TEAMCENTER_BASE_URL` | Integration only | Empty | Teamcenter web-tier context root; production requires HTTPS. |
| `TEAMCENTER_SERVICE_ROOT` | No | `RestServices` | Deployed Teamcenter REST service root. |
| `TEAMCENTER_AUTH_MODE` | No | `password` | Server-side `password` or `cookie` authentication. |
| `TEAMCENTER_USERNAME` / `TEAMCENTER_PASSWORD` | Password mode | Empty | Sensitive Teamcenter service-account credentials. |
| `TEAMCENTER_JSESSIONID` / `TEAMCENTER_XSRF_TOKEN` | Cookie mode | Empty | Sensitive session-bound Teamcenter cookies. |
| `TEAMCENTER_VERIFY_SSL` | No | `true` | Boolean or internal CA bundle; cannot be false in production. |
| `TEAMCENTER_MAX_RESPONSE_BYTES` | No | `10485760` | Maximum streamed Teamcenter response bytes. |
| `JIRA_URL` | Yes | None | Main JIRA base URL. |
| `AW_USERNAME` | No | Empty string | Sensitive integration username; keep external. |
| `AW_PASSWORD` | No | Empty string | Sensitive integration password; keep external. |
| `DATABASE_URL` | No | SQLite under `backend/` | Primary database URL. Use PostgreSQL in production. |
| `DB_OLD_URL` | No | SQLite under `backend/` | Legacy database URL. |
| `DATABASE_CONN_MAX_AGE` | No | `60` | Persistent connection age in seconds. |
| `CACHE_URL` | No | LocMem cache | Redis URL for production cache. |
| `COMPDOC_IMPORT_PREVIEW_TTL_SECONDS` | No | `900` | Signed CompDoc preview confirmation lifetime in seconds. |
| `DCC_PREVIEW_TTL_SECONDS` | No | `900` | Owner-bound DCC snapshot confirmation lifetime; runtime bounds it to 60-86400 seconds. |
| `LOG_LEVEL` | No | `INFO` | Console logging level. |
| `FRONTEND_RESET_URL` | No | Computed from debug, host, and port | Password reset frontend URL. |
| `FRONTEND_INVITATION_URL` | No | Computed `/app/invite` URL | Public registration screen used by one-time invitation links. |
| `TRUSTED_PROXY_COUNT` | No | `0` | Trusted reverse-proxy hops used for secure per-client throttling; set `1` for the bundled Nginx topology. |
| `ALLOWED_HOSTS` | No | `IPV4_ADDRESS`, `127.0.0.1`, `localhost` | Comma-separated list parsed by django-environ. |
| `CORS_ALLOWED_ORIGINS` | Production yes | Empty list | Required when `DEBUG=False`. |
| `CSRF_TRUSTED_ORIGINS` | No | Empty list | Add HTTPS origins for cross-origin form/cookie flows. |
| `AUTH_COOKIE_NAME` | No | `auth_token` | Cookie name for DRF token authentication. |
| `AUTH_COOKIE_MAX_AGE` | No | `1209600` | Cookie lifetime in seconds. |
| `AUTH_COOKIE_SAMESITE` | No | `Lax` in debug, `None` in production | Use `None` only with HTTPS secure cookies. |
| `AUTH_COOKIE_SECURE` | No | `False` in debug, `True` in production | Keep enabled for production. |
| `AUTH_TOKEN_RESPONSE_ENABLED` | No | Same as `DEBUG` | Disable in production unless a reviewed legacy need exists. |
| `SECURE_SSL_REDIRECT` | No | `False` in debug, `True` in production | Keep enabled behind HTTPS; disable only for local Compose without TLS. |
| `SECURE_HSTS_SECONDS` | No | `0` in debug, `31536000` in production | Production HSTS duration. |
| `SESSION_COOKIE_SECURE` | No | `False` in debug, `True` in production | Keep enabled for production sessions. |
| `CSRF_COOKIE_SECURE` | No | `False` in debug, `True` in production | Keep enabled for production CSRF cookies. |

## Required frontend build variables

| Variable | Required | Notes |
|---|---:|---|
| `VITE_API_URL` | Deployment-specific | Axios base URL for backend API calls. |
| `VITE_API_TIMEOUT_MS` | No | Axios request timeout in milliseconds; defaults to 10000. |
| `VITE_VERSION` | No | Displayed build/application version. |
| `VITE_APP_TITLE` | No | Application title used by the frontend. |

## Production bootstrap

Run the immutable image and migrations before accepting traffic. Frontend build, static collection,
and artifact verification already happen while the image is built:

```bash
docker compose build
docker compose run --rm backend python manage.py migrate --noinput
docker compose up -d
curl -fsS http://localhost:8080/health/ready/
curl -fsS http://localhost:8080/app/
```

The `worker` service runs `python manage.py run_job_worker`. Schedule
`python manage.py cleanup_jobs` at least every five minutes so expired, unconfirmed DCC snapshots
are promptly removed; the same command applies the configured terminal artifact retention window.
Backend and worker containers must mount the same `PRIVATE_MEDIA_ROOT` volume. This
directory must never be exposed by Nginx; downloads pass through owner-authorized Django views.
Local Word translation and analysis models are not baked into the image. Provision all four
configured model directories through the shared `/app/models` volume so both Integration Hub and
the worker see the same readiness state. Translation and explainable analysis run inside the
worker; document content is not sent to a cloud model. Analysis evidence is stored only in the
owner-authorized private job artifact.

Use `deploy/nginx/awcenter.conf` as a starting point for reverse proxy headers and route forwarding. Production TLS termination must set `X-Forwarded-Proto: https` so Django's `SECURE_PROXY_SSL_HEADER` can identify secure requests.

`python manage.py verify_frontend_artifact` is the deployment smoke command. It fails when the
Vite index is absent or oversized, references a missing/empty/unsafe JS or CSS file, collectstatic
output is stale, Django cannot serve a nested `/app/...` route, or WhiteNoise cannot serve entry
assets. CI runs the same command against both the workspace build and the combined runtime image.

## Security notes

- Do not copy `.env`, certificates, private keys, SQLite databases, or media files into container images.
- Use a secret manager or orchestrator-managed environment variables for production secrets.
- Keep `DEBUG=False`, HTTPS, secure cookies, HSTS, explicit CORS, and explicit CSRF trusted origins in production.
- Treat PostgreSQL credentials in `docker-compose.yml` as local placeholders only; replace them outside source control for shared environments.
