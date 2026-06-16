# AW Center Production Readiness Report

## Evidence scope

This report uses static evidence from `backend/awcenter/settings.py`, `backend/awcenter/authentication.py`, `backend/awcenter/api_errors.py`, `backend/awcenter/middleware.py`, `backend/awcenter/urls.py`, `frontend/src/services/http.ts`, `frontend/src/router/index.ts`, `frontend/package.json`, `requirements.txt`, and app-level Django files.

## Current state analysis

The repository contains several production-oriented controls: `DEBUG` defaults to false, `SECRET_KEY` is required when debug is false, CORS origins are required in production, secure cookies and HSTS are enabled outside debug, DRF defaults to authenticated access, and API errors are normalized. The frontend sends credentials on Axios requests and supports lazy route loading.

Production gaps remain around database choice, observability, structured logging, CI evidence, dependency governance, platform-specific integrations, and coverage for broad app-level behavior.

## Major improvements

| Improvement | Severity | Location | Explanation | Recommendation | Business value | Technical value | Complexity | Risk | Confidence | Rollback strategy | Testing strategy |
|---|---:|---|---|---|---|---|---|---|---|---|---|
| Add production database profile | Critical | `backend/awcenter/settings.py` | SQLite is configured as the default persistence layer. Enterprise multi-user workloads need stronger concurrency and recovery. | Support PostgreSQL via environment variables and document migration steps. | Reduces data-loss and downtime risk. | Enables robust transactions, indexes, and backup tooling. | Medium | Medium | High | Keep SQLite development default; switch by env only. | Django migration tests, backup/restore rehearsal, load test basic write paths. |
| Implement structured audit logging | High | `backend/awcenter/middleware.py` | Current request logging prints to stdout and is enabled only when `DEBUG=False`. It lacks structured fields, correlation IDs, and redaction rules. | Replace print logging with Python logging, request IDs, user IDs, latency, status, and sensitive-data redaction. | Improves incident response and compliance evidence. | Makes logs machine-queryable and safer. | Medium | Low | High | Keep old middleware disabled behind setting during transition. | Unit tests for redaction and middleware response logging. |
| Define deployment health checks | High | `backend/awcenter/urls.py`, settings | No explicit health/readiness endpoints are evident in the main router. | Add `/health/live/` and `/health/ready/` endpoints checking app boot, DB, cache, and critical configuration. | Faster operations and safer rollouts. | Enables load balancer and orchestration integration. | Low | Low | High | Health endpoints are additive. | Endpoint tests with DB available/unavailable simulation. |
| Harden dependency and runtime governance | High | `requirements.txt`, `frontend/package.json` | Backend requirements are bounded but not locked; frontend has a lock file. Native/NLP/Windows dependencies increase install risk. | Add dependency scanning, lock or constraints strategy, and SBOM generation. | Reduces supply-chain and release surprises. | Reproducible environments and easier vulnerability triage. | Medium | Low | High | Keep existing manifests while introducing constraints in CI first. | `pip check`, `npm audit --omit=dev`, and dependency installation CI. |
| Add CI quality gates | High | Repository scripts and tests | App-level tests are sparse across many apps. There is no visible lint or type-check script for frontend beyond installed tooling. | Add CI for Django checks/tests, frontend type-check/build, dependency audit, and docs checks. | Prevents release regressions. | Establishes repeatable verification. | Medium | Low | High | Start as non-blocking, then make gates required. | CI runs on pull requests with captured artifacts. |
| Document operational secrets and cookie policies | Medium | settings and frontend HTTP | Auth cookie behavior is configurable and Axios sends credentials. Operational teams need exact same-site/cross-site guidance. | Add deployment matrix for same-site HTTP dev, HTTPS same-site, and HTTPS cross-site SPA/API deployments. | Reduces failed logins and insecure overrides. | Makes auth behavior deterministic. | Low | Low | High | Documentation-only change. | Manual deployment checklist and auth smoke tests. |

## Prioritized to-do list

1. Add production database profile and migration checklist.
2. Add structured logging and health endpoints.
3. Introduce CI gates for backend checks/tests and frontend type-check/build.
4. Add dependency scanning and backend constraints strategy.
5. Document production cookie/CORS/CSRF deployment modes.

## Points requiring attention

- Production hardening must not weaken global `IsAuthenticated` defaults.
- Health endpoints must not leak secrets, dependency URLs, or internal paths.
- Logging must redact tokens, cookies, credentials, file names where sensitive, and uploaded content.
