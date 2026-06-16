# AW Center DevOps Review

## Evidence scope

This review uses static repository evidence from Django settings, URL routing, auth/error/middleware code, frontend router and HTTP services, Vite configuration, frontend package scripts, backend requirements, and app-level Django files.

## Current state analysis

The project has a deployable Django/Vite shape: Vite builds frontend assets, a postbuild step copies them into Django template/static directories, WhiteNoise is configured for static files, and Cheroot HTTPS serving exists. However, production operation needs stronger environment management, CI/CD, health checks, reproducible builds, logs, dependency scanning, and platform-specific dependency handling.

## Major improvements

| Improvement | Severity | Location | Explanation | Recommendation | Business value | Technical value | Complexity | Risk | Confidence | Rollback strategy | Testing strategy |
|---|---:|---|---|---|---|---|---|---|---|---|---|
| Add CI/CD pipeline | Critical | repository scripts, `frontend/package.json`, `requirements.txt` | No visible CI file is present in the reviewed evidence. | Run backend install/check/tests, frontend install/build/type-check, dependency audit, and artifact packaging on PRs. | Prevents broken releases. | Creates repeatable validation. | Medium | Low | High | Start as advisory checks before blocking merges. | CI status checks and retained logs/artifacts. |
| Create deployment environment matrix | High | `backend/awcenter/settings.py`, `frontend/src/services/http.ts` | Cookie, CORS, CSRF, HTTPS, and frontend API base URL behavior depend on deployment topology. | Document and validate local, same-site HTTPS, and cross-site HTTPS profiles. | Fewer deployment incidents. | Clear configuration contract. | Low | Low | High | Documentation can be amended without code rollback. | Environment smoke tests for login and protected requests. |
| Health, readiness, and metrics | High | `backend/awcenter/urls.py`, settings | Operations need explicit health endpoints and basic metrics. | Add live/ready endpoints and metrics-compatible logging or exporter. | Faster incident detection and safer rollouts. | Better observability. | Medium | Low | High | Endpoints are additive and can be restricted. | Health endpoint tests and orchestration probe tests. |
| Build artifact discipline | High | `frontend/scripts/postbuild.js`, Django static settings | Frontend build copies assets into backend directories. Generated output should not be accidentally committed. | Ensure build outputs are ignored, artifacts are packaged by CI, and postbuild target dirs are validated. | Reproducible releases. | Avoids dirty working trees and stale assets. | Low | Low | High | Keep current local build behavior while moving packaging to CI. | Build command plus git-status cleanliness check. |
| Dependency vulnerability management | High | `requirements.txt`, `frontend/package-lock.json` | Backend is not locked; frontend is locked. Native dependencies may be platform-sensitive. | Add scheduled dependency scans, lock/constraints policy, and upgrade cadence. | Reduces supply-chain risk. | Predictable installs and vulnerability triage. | Medium | Low | High | Scans can be advisory first. | `pip check`, vulnerability scanner, `npm audit --omit=dev`. |
| Secret management and release checklist | High | settings and environment variables | Many env vars represent secrets or integration endpoints. | Use a secret manager, `.env` only for local dev, and release checklist for required variables. | Prevents credential leakage and misconfiguration. | Consistent deploys. | Medium | Low | High | Keep current env loading; change sourcing per environment. | Startup config validation tests and deployment dry-run. |

## Prioritized to-do list

1. Add CI for backend and frontend verification.
2. Add health/readiness endpoints and deployment smoke tests.
3. Document environment matrix and secret management rules.
4. Add dependency scanning and backend constraints strategy.
5. Ensure build artifacts are generated in CI and not committed.

## Rollout strategy

Start with non-invasive CI and documentation. Then add health endpoints and logging. Finally, standardize artifact packaging and dependency governance. This sequencing avoids blocking feature teams while improving release safety.
