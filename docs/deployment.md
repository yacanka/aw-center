# Deployment Foundations

This repository now includes container and CI foundations for AW Center. The files are intentionally conservative: secrets, certificates, SQLite databases, media uploads, generated static files, and dependency folders are excluded from images and source control.

## Container images

- `backend/Dockerfile` builds a Django runtime from the repository-level `requirements.txt` and runs `backend/manage.py` from `/app`.
- `frontend/Dockerfile` uses a multi-stage Node build for Vite assets and serves the compiled `dist/` directory with Nginx.
- `.dockerignore` excludes local runtime artifacts and secrets from Docker build contexts.

## Local orchestration

Use Docker Compose from the repository root:

```bash
docker compose up --build
```

Services:

| Service | Purpose | Local port |
|---|---|---|
| `backend` | Django runtime | `8000` |
| `frontend` | Nginx-served Vite static assets | `8080` |
| `database` | PostgreSQL production-grade database candidate | `5432` |

The current Django settings still default to SQLite. PostgreSQL is included as the production-grade database candidate so migrations, backup strategy, and settings migration can be introduced deliberately instead of silently changing persistence behavior.

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
| `JIRA_LEGACY_URL` | Yes | None | Legacy JIRA base URL. |
| `JIRA_BTB_URL` | Yes | None | Main JIRA base URL. |
| `AW_USERNAME` | No | Empty string | Sensitive integration username; keep external. |
| `AW_PASSWORD` | No | Empty string | Sensitive integration password; keep external. |
| `FRONTEND_RESET_URL` | No | Computed from debug, host, and port | Password reset frontend URL. |
| `ALLOWED_HOSTS` | No | `IPV4_ADDRESS`, `127.0.0.1`, `localhost` | Comma-separated list parsed by django-environ. |
| `CORS_ALLOWED_ORIGINS` | Production yes | Empty list | Required when `DEBUG=False`. |
| `CSRF_TRUSTED_ORIGINS` | No | Empty list | Add HTTPS origins for cross-origin form/cookie flows. |
| `AUTH_COOKIE_NAME` | No | `auth_token` | Cookie name for DRF token authentication. |
| `AUTH_COOKIE_MAX_AGE` | No | `1209600` | Cookie lifetime in seconds. |
| `AUTH_COOKIE_SAMESITE` | No | `Lax` in debug, `None` in production | Use `None` only with HTTPS secure cookies. |
| `AUTH_COOKIE_SECURE` | No | `False` in debug, `True` in production | Keep enabled for production. |
| `AUTH_TOKEN_RESPONSE_ENABLED` | No | Same as `DEBUG` | Disable in production unless a reviewed legacy need exists. |
| `SECURE_HSTS_SECONDS` | No | `31536000` when `DEBUG=False` | Production HSTS duration. |

## Required frontend build variables

| Variable | Required | Notes |
|---|---:|---|
| `VITE_API_URL` | Deployment-specific | Axios base URL for backend API calls. |
| `VITE_VERSION` | No | Displayed build/application version. |
| `VITE_APP_TITLE` | No | Application title used by the frontend. |

## Security notes

- Do not copy `.env`, certificates, private keys, SQLite databases, or media files into container images.
- Use a secret manager or orchestrator-managed environment variables for production secrets.
- Keep `DEBUG=False`, HTTPS, secure cookies, HSTS, explicit CORS, and explicit CSRF trusted origins in production.
- Treat PostgreSQL credentials in `docker-compose.yml` as local placeholders only; replace them outside source control for shared environments.
