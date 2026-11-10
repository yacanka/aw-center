# Management Reports first release

## Intent and approved scope

The user approved executive summary, weekly comparison and PDF reporting, preserving the existing dashboard and entering through a separate application/menu area. Implement a Django `management_reports` app and a lazy Vue `/management-reports` screen within AW Center. Existing CompDoc routes and payloads remain compatible.

## Approach

Use the existing common CompDoc aggregation for the executive metrics, with an independent read/report layer. Persist server-calculated, owner-scoped report snapshots; generate PDF downloads from those snapshots. Reusing the existing dashboard screen would not meet the separate-area request. A separate deployment or external BI service adds infrastructure without helping this release. The app/module approach follows the user's chosen separation; the detailed engineering choices below are implementation decisions.

## Data and access

- Only enabled registry projects declaring `compdocs` are eligible. The user must currently hold the concrete model's `view_compdoc` permission for every selected project. Do not expose technical registry metadata.
- Routes and menu use authenticated access. The app presents an empty state when there are no authorized projects. API authorization is authoritative.
- Snapshots belong to their creator. List, detail, comparison and PDF recheck current project access; another owner's UUID returns 404. No sharing, update or delete API in this release.
- Snapshot: UUID, owner, captured_at, Monday week_start, schema_version=1, SHA-256 scope_key over sorted unique project slugs, JSON payload. Metrics and timestamps are server controlled. Clients submit title (120 chars), management_note (2000 chars), and nonempty unique project_slugs only.
- Multiple snapshots in one week are allowed. Captured reports never change through the API.
- No migrations are applied to the user's database automatically.

## Metrics and comparison

Report metrics: document_count, issued_count, approved_count, approval_percentage (one decimal), scheduled_count, schedule_variance (issued minus scheduled), high_risk_count, action_overdue_count, action_due_soon_count, unassigned_count, pending_review_count, pending_approval_count, data_quality_issue_count. Approval percentage is total approved / total documents, not the mean of project percentages. Zero documents yields 0% and an explicit empty portfolio state.

Use existing CompDoc status, risk and operational definitions. Keep published and authority-approved counts separate. Data-quality values count issues, not unique documents. Snapshot time is the capture time, not an external integration freshness timestamp.

Default baseline is the latest same-owner, identical-scope, identical-schema snapshot from the immediately preceding Monday-Sunday calendar week. Missing baseline means available=false and null deltas, never zero. An explicit baseline UUID may choose any older compatible snapshot. Current/baseline times and elapsed days are displayed. Differences are net stock changes, not event throughput. Scope, chronology, schema mismatch and inaccessible baselines are rejected.

Top five risk priorities supplement metrics, with document/project identity, explainable reason, stage age, owner and next-action date. They are document priorities, not asserted management decisions. A bounded management note records the author's context/decision request. No invented forecast, milestone health score or automatic narrative.

## API contract

Base `/management-reports/` (the existing HTTP service supplies the API prefix).

- GET `options/` -> `{projects: [{slug, display_name}]}`.
- GET `overview/?projects=slug,slug` -> ReportEnvelope.
- GET `reports/?projects=slug,slug&page=1` -> `{count, next, previous, results: ReportListItem[]}`; page size 20. Omitted scope lists all accessible own reports.
- POST `reports/` with `{project_slugs, title, management_note}` -> ReportEnvelope (201).
- GET `reports/<uuid>/?baseline=<uuid>` -> ReportEnvelope.
- GET `reports/<uuid>/pdf/?baseline=<uuid>` -> application/pdf attachment; identical saved report and baseline semantics. In-memory output only, no public media file.

ReportEnvelope = `{report: Report, comparison: Comparison}`.
Report = `{id: string|null, title, management_note, captured_at, week_start, schema_version, project_slugs, totals: Metrics, projects: ProjectMetrics[], priorities: Priority[]}`.
ProjectMetrics = `{slug, display_name, ...Metrics}`.
Comparison = `{available, baseline: ReportListItem|null, elapsed_days: number|null, deltas: Metrics|null}`. Each delta uses the same metric key; approval_percentage is percentage points.
ReportListItem = `{id, title, captured_at, week_start, schema_version, project_slugs}`.
Priority = `{document_id, project_slug, project_name, name, status, score, level, stage_age_days, reason, owner, next_action_due_date}`.

## Interface

Match existing Naive UI and application theme; no external font/network requests in the browser. Separate Management Reports menu and command-search entry. Multi-project selector, refresh, server-side save, history selection and saved PDF download. Show live vs saved state clearly; changing scope resets saved selection/comparison. Loading and request cancellation prevent stale responses replacing a different selection.

Executive KPI cards, project comparison table and horizontal approval bars use the same source metrics. Weekly comparison cards show signed net differences and actual baseline dates. Saved-report history is paginated. Empty/no-permission/error/no-baseline states are explicit. Small screens stack cards and retain readable scrollable tables.

## PDF and dependencies

`management_reports.pdf.build_report_pdf(report, comparison) -> bytes` uses ReportLab (BSD licensed) for searchable vector PDF without browser-print dependencies. Existing pypdf reads PDFs but is not a document-layout engine. ReportLab is the sole new direct Python dependency; update requirements.in and regenerate requirements.txt with pip-compile without upgrading unrelated locks. Bundle official Noto Sans regular/bold with OFL license for reproducible Turkish text across Windows/Linux/macOS. No frontend dependency is needed.

PDF includes capture time, scope, KPI cards, comparison/baseline, project overview, top priorities, management note, metric definitions and page numbers. Prefer a one-page overview; long notes/priorities continue safely to additional pages. Escape all user-controlled text for ReportLab paragraphs. Do not truncate important notes silently.

## Verification and boundaries

Test unauthenticated/unauthorized requests, owner isolation and revoked access, disabled/unknown projects, duplicate/empty/oversized scope, server-controlled payload, weighted totals, missing/compatible/incompatible baseline, calendar-week edges, immutable snapshots, pagination, PDF access and Unicode text. Verify frontend helpers, menu/route policy and async scope safety; run typecheck, formatting, Node suite and production build. Render a representative PDF for visual inspection and inspect responsive UI where runtime permits.

This release does not schedule snapshot capture, send reports, create shared report access, change CompDoc workflows, or build JIRA history/forecasting.
