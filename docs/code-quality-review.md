# AW Center Code Quality Review

## Evidence scope

This review is based on static repository evidence from backend settings, URL routing, auth/error/middleware modules, frontend router, Axios service, Vite/package configuration, backend requirements, and app-level Django models, views, serializers, and tests.

## Current state analysis

The codebase shows several quality improvements already in place: centralized API error utilities, documented auth cookie helpers, route-level lazy loading, manual vendor chunking, and frontend HTTP credential defaults. At the same time, the repository has broad app-level modules, several placeholder tests, no visible Python formatter/linter configuration, and no frontend lint/type-check scripts in `package.json`.

## Major improvements

| Improvement | Severity | Location | Explanation | Recommendation | Business value | Technical value | Complexity | Risk | Confidence | Rollback strategy | Testing strategy |
|---|---:|---|---|---|---|---|---|---|---|---|---|
| Define automated formatting and linting | High | repository root, frontend package | Formatting/linting tools are not visible for Python; frontend has Prettier config but no script. | Add Ruff/Black or Ruff-format for Python and npm scripts for Prettier/type-checking. | Faster reviews and consistent code. | Reduces style churn and simple defects. | Low | Low | High | Run in check-only mode first. | CI lint jobs and local commands. |
| Enforce module complexity limits | High | app `views.py`, `serializers.py` | Large modules and long functions are hard to review securely. | Add complexity checks and refactor endpoints into services/selectors. | Lower maintenance cost. | Easier unit tests and code ownership. | Medium | Medium | Medium | Apply thresholds to changed files first. | Complexity report in CI. |
| Improve test density outside users | High | app `tests.py` | Several app tests are placeholders. | Add permission, serializer, and smoke tests by domain. | Better confidence for enterprise users. | Prevents regressions during refactoring. | Medium | Low | High | Tests are additive. | Django test suite by changed app. |
| Strengthen type boundaries | Medium | `frontend/src/services/http.ts`, app serializers | Backend and frontend contracts should be explicit. | Add TypeScript DTOs and backend serializer contract tests. | Reduces integration defects. | Makes refactors safer. | Medium | Low | Medium | Start with high-use endpoints. | Type-check and API contract tests. |
| Use structured logging and error taxonomy | Medium | `api_errors.py`, middleware, app views | API error contract exists, but domain-specific error codes should be expanded. | Maintain an error-code registry and replace ad hoc errors incrementally. | Better support and user messaging. | Consistent client handling. | Medium | Low | High | Keep generic `ERROR` fallback. | Error contract tests and frontend formatter tests. |
| Document public functions and services | Low | new service modules | Some public helpers are documented; this should become the norm for extracted services. | Require docstrings for public Python functions and JSDoc for shared TypeScript helpers. | Easier onboarding. | Better maintainability. | Low | Low | Medium | Documentation can be added incrementally. | Documentation lint/check where practical. |

## Prioritized to-do list

1. Add check-only lint/format/type scripts.
2. Add tests around changed endpoints before refactoring.
3. Extract high-risk view logic into small services.
4. Add frontend DTOs for core API calls.
5. Expand domain-specific error codes.

## Clean-code guardrails

- Keep functions short and single-purpose.
- Prefer explicit permission checks and named policies.
- Avoid database access inside loops; use `select_related`, `prefetch_related`, and pagination.
- Keep upload validation centralized and deny by default.
- Preserve existing contracts unless versioned migration is documented.
