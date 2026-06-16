# AW Center Architecture Review

## Evidence scope

This review is based on static repository evidence from Django project settings, URL routing, authentication, error middleware, Vue Router, Axios configuration, Vite configuration, package manifests, backend requirements, and app-level `models.py`, `views.py`, `serializers.py`, and `tests.py` files.

## Current state analysis

AW Center is a Django REST-oriented backend with a Vue 3/Vite frontend mounted under `/app/`. The backend groups domain capabilities into Django apps such as `dcc`, `ddf`, `doors`, `docproof`, `excel`, `word`, `pdf`, `outlook`, `orgs`, `pptxgallery`, `releases`, `users`, and project-specific apps. The frontend uses route-level lazy loading for most non-critical screens and Axios defaults for backend communication.

Positive architectural signals include explicit Django app boundaries, centralized DRF authentication and permission defaults, a shared API error contract, route-level code splitting, and documented cookie-auth defaults. Key risks are the breadth of file-processing endpoints, a large URL surface, SQLite persistence for an enterprise workflow domain, mixed API styles across legacy apps, and sparse app-level tests outside the user/security area.

## Major improvements

| Improvement | Severity | Location | Explanation | Recommendation | Business value | Technical value | Complexity | Risk | Confidence | Rollback strategy | Testing strategy |
|---|---:|---|---|---|---|---|---|---|---|---|---|
| Establish bounded-context API contracts | High | `backend/awcenter/urls.py`, app `views.py`, app `serializers.py` | The URL router exposes many domain apps directly, while app-level views likely evolved independently. This increases inconsistent request/response shapes. | Define per-domain API contracts, owners, DTOs, and versioning rules. Start with `users`, `dcc`, `ddf`, and file-processing apps. | Safer enterprise integrations and easier audit sign-off. | Reduces coupling and regression scope. | Medium | Medium | High | Keep existing routes and add compatibility adapters before removing legacy shapes. | Contract tests per endpoint family plus frontend smoke tests. |
| Move production persistence away from SQLite | High | `backend/awcenter/settings.py` | The static settings configure SQLite databases for default and old data. SQLite is useful for local development but weak for concurrent enterprise workflows. | Add environment-driven PostgreSQL configuration while keeping SQLite as local default. | Better reliability, backups, concurrency, and compliance readiness. | Enables indexing, observability, and stronger transactional behavior. | Medium | Medium | High | Feature-flag database settings; retain SQLite local profile. | Migration dry-runs, backup/restore drill, integration tests against PostgreSQL. |
| Standardize long-running document workflows | High | `excel`, `word`, `pdf`, `pptxgallery`, `doors`, app `views.py` | Office/PDF/DOORS workflows are likely CPU, IO, and platform dependent. Synchronous requests can time out and make failures hard to audit. | Introduce a job abstraction with status, artifacts, retry policy, timeout, owner, and audit events. | Predictable user experience for expensive compliance operations. | Clear separation between API, worker, and artifact storage. | High | Medium | Medium | Run job endpoints alongside synchronous endpoints until migrated. | Worker unit tests, timeout tests, artifact lifecycle tests, end-to-end upload/job/download tests. |
| Expand route authorization metadata | Medium | `frontend/src/router/index.ts`, backend permissions | Some frontend routes declare `meta.auth`, but many business-sensitive routes rely mainly on backend authorization. | Define route metadata for auth, feature, and role requirements and align with backend permissions. | Reduces accidental exposure of sensitive UI areas. | Makes authorization intent visible and reviewable. | Low | Low | High | Keep backend as authority; route metadata can be disabled per route. | Router guard unit tests and protected-route Cypress/Playwright smoke tests when available. |
| Create architecture decision records | Medium | `docs/` | Architectural decisions such as cookie auth, static serving, job handling, and database choice need traceability. | Add ADRs for authentication, deployment topology, database strategy, and document-processing architecture. | Better onboarding and audit evidence. | Prevents repeated design debates and drift. | Low | Low | High | ADRs are additive and can be superseded. | Documentation review checklist in PRs. |

## Prioritized to-do list

1. Define API contract and ownership for `users`, `dcc`, `ddf`, and document-processing endpoints.
2. Add environment-selectable PostgreSQL settings for production.
3. Design a shared job model for long-running document workflows.
4. Align frontend route metadata with backend permission policies.
5. Add ADRs for major platform decisions.

## Trade-offs and alternatives

- A full API versioning initiative gives strong governance but requires more coordination than adding contract tests around existing routes.
- PostgreSQL improves production readiness but adds local setup and CI service complexity.
- A task queue adds operational components; a database-backed job table without external workers is simpler but less scalable.
