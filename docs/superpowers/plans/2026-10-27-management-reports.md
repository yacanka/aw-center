# Management Reports Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Deliver a separate management reporting app with executive portfolio metrics, weekly net comparisons and downloadable saved-report PDFs.

**Architecture:** A Django management_reports app reuses common CompDoc builders, stores private immutable snapshots, and validates every project permission on access. A separate lazy Vue screen uses the existing authenticated HTTP and Naive UI infrastructure. ReportLab generates PDFs from the same saved data.

**Tech Stack:** Django/DRF, Vue 3/TypeScript/Naive UI, ReportLab, existing Django and Node test runners.

**Spec:** docs/superpowers/specs/2026-10-27-management-reports-design.md

## Global Constraints

- Preserve existing CompDoc routes, aggregation semantics and dashboard behavior.
- CPython 3.11+ compatibility; no user database migrations during implementation.
- Only enabled CompDoc projects and current project view permissions; report ownership on every read/export.
- Snapshot metrics/timestamps are server controlled; API snapshots are immutable.
- Keep standard cookie authentication/CSRF and API error contract.
- Preserve unrelated frontend/test-results/ and private_media/ local files.

## Review Focus

- Permission revocation after capture must hide saved report details and PDFs.
- A missing previous-week snapshot must not produce misleading zero deltas.
- Scope additions/removals must not be compared as like-for-like weekly reports.
- Long Turkish notes and labels must remain legible and complete in PDF.
- Rapid scope/report changes must not display stale data or export the wrong report.

### Task 1: Backend reporting domain and API

Files: new backend/management_reports app, models/migration, access/aggregation/comparison services, serializers, views, urls and tests; backend/awcenter/settings.py and urls.py; extract shared operational summary only if needed.

Interfaces: implement ReportEnvelope and endpoints exactly as the spec; PDF view calls `management_reports.pdf.build_report_pdf(report, comparison)` lazily.

- [x] Write API/aggregation/access/comparison tests and observe missing feature failures.
- [x] Implement app, snapshot migration and permission-scoped report services.
- [x] Verify owner isolation, permission revocation, week boundaries, schema/scope chronology, pagination and payload validation.
- [x] Run `.venv/bin/python backend/manage.py test management_reports common.test_compdoc_dashboard` with appropriate cwd; run Django checks and migration drift checks.

### Task 2: Frontend reporting application

Files: frontend/src/models/managementReports.ts, services/managementReports.ts, pure reporting helper module if needed, views/ManagementReports.vue and focused components/composable; routes.ts, mainMenu.ts, accessPolicy.ts, commandSearch.ts; frontend/scripts/test-management-reports.mjs, test-route-access.mjs and package.json.

Interfaces: consumes the spec's ReportEnvelope/API; GET options is the only authorized project source; downloads saved report bytes by UUID.

- [x] Write meaningful helper/navigation/request behavior tests; observe feature failures.
- [x] Implement portfolio cards/table/bars, weekly deltas, report capture/history/PDF, explicit loading/error/empty states and stale-request guards.
- [x] Check formatting, typecheck, reporting/access tests and production build; preserve existing dashboard source.

### Task 3: PDF generation and dependency manifest

Files: backend/management_reports/pdf.py, test_pdf.py, fonts/NotoSans-Regular.ttf, fonts/NotoSans-Bold.ttf, fonts/OFL.txt and provenance README; requirements.in and generated requirements.txt.

Interfaces: `build_report_pdf(report: dict, comparison: dict) -> bytes`; no persistent filesystem output in production.

- [x] Add PDF text/access/Unicode/long-content tests and observe missing implementation failure.
- [x] Add ReportLab via manifest resolver and bundle upstream font with license.
- [x] Implement layout with escaped text and safe pagination, render representative PDF and inspect all pages.
- [x] Verify searchable content, no clipping, long text and empty portfolio.

### Task 4: Integration and verification

Files: docs/architecture.md or focused docs/management-reports.md, plan progress; targeted fixes only.

- [x] Review final changes independently against spec, especially access, comparison semantics and PDF/UI consistency.
- [x] Run launcher check/test, frontend formatting/typecheck/test:ci/build, Django migration drift checks and report any unrelated existing failures.
- [x] Verify responsive interface and real PDF download via temporary test-only data/session where feasible; never mutate the user's database.
- [x] Document save/compare/PDF usage and required migration/setup action; do not auto-migrate or commit user data.

## Execution record

- User approved the first-release proposal and specified an independent menu/application area. Engineering choices are documented in the spec; proceed in this chat under that authorization.
- Ruling: work in the current user-provided checkout, retaining unrelated local artifacts; no branch/history mutations are needed for delivery.
- Backend and frontend implementation ownership is disjoint; parallel execution follows the active multi-agent instruction. Root owns PDF/dependencies/integration and final independent review.
- Tasks 1-4 implemented and verified. See `2026-10-27-management-reports-verification.md` for checks, existing full-suite failures and required deployment migration.
- Ruling: direct ReportLab PDF with packaged Noto Sans meets the requested download without browser print steps; source/pins/licenses are documented.
- Ruling: restrict compact mobile shell behavior to the new report route; the shared menu otherwise preserves its prior presentation.
