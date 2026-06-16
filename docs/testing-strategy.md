# AW Center Testing Strategy

## Evidence scope

This strategy is based on static repository evidence from backend settings, DRF auth/error handling, middleware, URL routing, frontend router and Axios configuration, Vite/package scripts, requirements, and app-level Django `models.py`, `views.py`, `serializers.py`, and `tests.py` files.

## Current state analysis

The repository has Django tests, with meaningful coverage visible in the user/security area and placeholder tests in several apps. Frontend dependencies include TypeScript and `vue-tsc`, but `package.json` does not define a dedicated type-check or test script. Backend checks can be run through Django when dependencies and environment variables are available.

## Major improvements

| Improvement | Severity | Location | Explanation | Recommendation | Business value | Technical value | Complexity | Risk | Confidence | Rollback strategy | Testing strategy |
|---|---:|---|---|---|---|---|---|---|---|---|---|
| Add backend smoke tests per mounted app | High | `backend/awcenter/urls.py`, app `tests.py` | Many apps are routable but have placeholder tests. | Add authenticated and unauthenticated smoke tests for each app's critical endpoints. | Catches broken releases early. | Establishes baseline behavior before refactoring. | Medium | Low | High | Tests are additive and can start non-blocking. | Django `manage.py test` by app. |
| Build API contract tests | High | app `serializers.py`, `views.py`, `api_errors.py` | Enterprise integrations depend on stable payloads. | Assert status codes, fields, error contract, pagination, and auth behavior. | Prevents costly integration breakage. | Documents API behavior executable form. | Medium | Low | High | Version tests alongside endpoint migration. | DRF APIClient tests with fixtures/factories. |
| File-processing security tests | Critical | `excel`, `word`, `pdf`, `outlook`, `pptxgallery`, `doors` | Upload and conversion endpoints are high-risk. | Test size limits, extension/MIME allowlists, safe paths, cleanup, and subprocess timeouts. | Reduces security incident risk. | Hardens common vulnerability surfaces. | Medium | Medium | Medium | Start with validators independent of external binaries. | Unit tests for validators and integration tests with small sample files. |
| Frontend type-check and route tests | Medium | `frontend/package.json`, `frontend/src/router/index.ts` | TypeScript tooling exists, but scripts do not expose type-checking. | Add `typecheck`, route guard tests, and service tests with mocked Axios. | Reduces UI regressions. | Improves confidence in auth and API contracts. | Low | Low | High | Add scripts without blocking builds initially. | `npm run typecheck`, component/router tests when runner is added. |
| End-to-end critical journeys | Medium | frontend routes and backend APIs | Login, document upload, compare, and report flows need integrated verification. | Add Playwright or Cypress for smoke journeys after stable test env exists. | Validates real user workflows. | Catches integration gaps across stack. | Medium | Medium | Medium | Keep E2E smoke suite small. | Login/logout, protected route, one upload workflow, one dashboard workflow. |
| Performance regression tests | Medium | list endpoints and document workflows | Pagination and file processing can degrade with data volume. | Add query-count tests and synthetic dataset benchmarks for critical lists. | Protects user experience as data grows. | Finds N+1 and memory issues. | Medium | Low | Medium | Use thresholds per endpoint and tune gradually. | Query count assertions and timed smoke benchmarks. |

## Test pyramid

1. **Unit tests:** validators, serializers, selectors, DTO formatters, auth helpers.
2. **Integration tests:** DRF endpoints, database interactions, file workflows with sample artifacts.
3. **Contract tests:** API response shape, error contract, pagination, auth policies.
4. **E2E smoke tests:** login, protected navigation, core document workflow.
5. **Operational checks:** Django check, frontend build/type-check, dependency audit, health endpoints.

## Minimum release gate proposal

- `python manage.py check`
- `python manage.py test users awcenter`
- App-specific Django tests for changed backend modules
- `npm run build` for frontend-affecting changes
- Future: `npm run typecheck`, dependency audit, and E2E smoke tests
