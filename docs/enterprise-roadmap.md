# AW Center Enterprise Roadmap

## Evidence scope

This roadmap is based on static repository evidence from Django settings and URLs, centralized authentication and error handling, frontend router and Axios setup, Vite/package configuration, backend requirements, and app-level Django models, views, serializers, and tests.

## Current state analysis

AW Center already reflects an enterprise workflow product: it integrates compliance documents, JIRA/DCC, DDF, DOORS, Office/PDF tooling, Outlook parsing, organization data, release notes, and project-specific modules. The next maturity step is to turn this broad functional surface into a governed enterprise platform with strong contracts, operations, auditability, and extensibility.

## Roadmap themes

| Improvement | Severity | Location | Explanation | Recommendation | Business value | Technical value | Complexity | Risk | Confidence | Rollback strategy | Testing strategy |
|---|---:|---|---|---|---|---|---|---|---|---|---|
| Platform governance and API ownership | High | `backend/awcenter/urls.py`, app modules | Many apps are mounted directly. Without ownership rules, enterprise change control becomes fragile. | Define domain owners, API lifecycle states, review checklists, and deprecation policy. | Improves predictability for users and integrations. | Reduces accidental breaking changes. | Medium | Low | High | Governance can start as documentation before enforcement. | API compatibility test suite. |
| Enterprise identity integration | High | `users`, authentication, settings | Token/cookie auth is local. Enterprise deployments often need SSO, MFA, and centralized lifecycle controls. | Add SAML/OIDC integration plan while preserving DRF token compatibility for automation where needed. | Meets enterprise security expectations. | Centralizes identity and offboarding. | High | Medium | Medium | Keep local auth as fallback during pilot. | SSO sandbox tests, role mapping tests, logout/session invalidation tests. |
| Audit and traceability model | High | app `models.py`, `simple_history`, middleware | `django-simple-history` is installed and middleware is present, but cross-domain audit semantics need standardization. | Define audit events for document changes, generated artifacts, external calls, approvals, and exports. | Stronger certification and audit evidence. | Consistent event model and reporting. | Medium | Medium | High | Add audit events incrementally by domain. | Event creation tests and report reconciliation checks. |
| Workflow orchestration layer | High | document-processing apps | Multiple domains execute document and integration workflows. | Introduce workflow/job orchestration with states, retries, artifacts, and owner visibility. | Improves reliability of high-value engineering workflows. | Decouples request handling from processing. | High | Medium | Medium | Start with one domain and keep existing endpoints. | State-machine tests and failure-injection tests. |
| Reporting and analytics foundation | Medium | `orgs`, `releases`, project apps | Compliance dashboards require trusted, normalized metrics. | Create read models/materialized views for KPIs and traceability reports. | Better management insight and audit readiness. | Avoids expensive ad hoc queries. | Medium | Low | Medium | Keep source tables unchanged. | Query correctness tests and performance baselines. |
| Plugin/integration framework | Medium | app structure and requirements | Integrations are domain-specific. Future enterprise adoption may need configurable connectors. | Define connector interfaces for JIRA, DOORS, DocProof, Office conversion, and file stores. | Easier customer-specific integration. | Isolates vendor-specific behavior. | High | Medium | Medium | Wrap existing integrations first without rewriting. | Contract tests with mocked external systems. |

## Suggested phases

1. **Foundation:** API governance, production database, CI gates, structured logging.
2. **Security:** SSO/MFA plan, role model, audit event standard, file-processing hardening.
3. **Reliability:** Job orchestration, health/readiness, observability, backup drills.
4. **Scale:** Reporting read models, server-side pagination everywhere, performance baselines.
5. **Extensibility:** Connector interfaces and customer-specific configuration strategy.

## Alternative approaches

- A monolithic governed platform is simpler operationally; extracting services is premature until clear scaling boundaries emerge.
- Workflow orchestration can start with Django database-backed jobs before adopting Celery, RQ, or a managed queue.
