# AW Center Refactoring Plan

## Evidence scope

This plan uses static evidence from project settings, URL routing, authentication, API error utilities, middleware, frontend router and HTTP services, Vite/package configuration, requirements, and app-level `models.py`, `views.py`, `serializers.py`, and `tests.py`.

## Current state analysis

The repository has clear domain app folders, but the breadth of app-level views and serializers suggests incremental feature growth. Several test files are placeholders, while user/security tests are more complete. Refactoring should be evolutionary, preserve URL contracts, and target safety, testability, and consistency before cosmetic cleanup.

## Major improvements

| Improvement | Severity | Location | Explanation | Recommendation | Business value | Technical value | Complexity | Risk | Confidence | Rollback strategy | Testing strategy |
|---|---:|---|---|---|---|---|---|---|---|---|---|
| Split large view modules by use case | High | app `views.py`, project `compdocs/views.py` | Large view modules make security and regression review difficult. | Move logic into small services/selectors/actions and keep views as request/response adapters. | Faster feature delivery with lower defect risk. | Lower complexity and better unit testing. | Medium | Medium | High | Move one endpoint family at a time; keep routes stable. | Characterization tests before extraction and endpoint tests after. |
| Centralize file-upload validation | High | `excel`, `word`, `pdf`, `outlook`, `pptxgallery`, `doors` views | File endpoints are security-sensitive and likely repeat validation. | Add shared validators for size, extension, MIME, safe names, temp cleanup, and scan hooks. | Reduces breach and data-leak risk. | Removes duplicated defensive code. | Medium | Medium | Medium | Gate validators per endpoint with compatibility options. | Malicious filename tests, oversized file tests, unsupported MIME tests. |
| Normalize serializers and DTOs | Medium | app `serializers.py` | Serializer conventions vary by app. | Define base serializer patterns for list/detail/write and avoid exposing privilege fields by default. | Stable contracts for frontend and integrations. | Reduces accidental field exposure. | Medium | Low | Medium | Keep old serializers and introduce new ones per endpoint. | Snapshot/contract tests for response fields. |
| Replace print middleware with logging service | Medium | `backend/awcenter/middleware.py` | Print statements are difficult to route and redact. | Use structured logging helper and middleware tests. | Better production support. | Cleaner observability code. | Low | Low | High | Feature flag structured logging. | Unit tests for request metadata and redaction. |
| Modularize frontend API access | Medium | `frontend/src/services/http.ts`, stores and views | Axios defaults are centralized, but domain API calls should be consistently grouped. | Create domain service modules with typed request/response DTOs. | Fewer UI regressions and clearer ownership. | Better TypeScript leverage. | Medium | Low | Medium | Keep old functions as wrappers during migration. | Type-check plus mocked service tests. |
| Reduce app-level placeholder tests | Medium | app `tests.py` | Many apps contain placeholder tests. | Replace placeholders with smoke, permission, and serializer tests per domain. | Better release confidence. | Documents expected behavior. | Medium | Low | High | Tests are additive. | Django test suite by app. |

## Prioritized to-do list

1. Add characterization tests for the highest-risk file and auth endpoints.
2. Extract shared file validation utilities.
3. Refactor one large view module into services/selectors while preserving routes.
4. Introduce typed frontend domain API services.
5. Replace placeholder app tests incrementally.

## Refactoring rules

- Preserve public routes and response shapes unless a migration plan exists.
- Keep security checks in or near the view layer and duplicate them in service tests where appropriate.
- Avoid large rewrites; prefer strangler-style extraction.
- Do not introduce new dependencies until current manifests and CI gates can verify them.
