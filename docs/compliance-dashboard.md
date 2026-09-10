# Compliance dashboard

The Compliance Docs home at `/app/compdocs/home` uses the authenticated,
project-role-protected `GET /api/projects/<slug>/compliance-documents/dashboard/`.
`compliance.dashboard` owns the read-only aggregation of canonical documents and
sequence-ordered `WorkflowEvent` records. Table pagination does not limit analytics.

The response preserves `project`, `total`, `archived`, `overdue` and canonical
`status_counts`. Added fields include `chart_status_counts`, `timeline`,
`performance`, `pending_days`, `risk`, `data_quality`, `generated_at` and `panels`.
Each panel includes its stable `id`, display `panel`, `ata` and `analytics` with
the same active-document metrics as the project. `unassigned` identifies documents
without a panel. Archived documents contribute only to the project archive count.

Double-clicking a panel row, or selecting it with Enter/Space, focuses all charts,
performance metrics, active counts, quality signals and risk priorities together.
Repeating the selection or closing the scope tag restores project totals. The panel
table always shows all project panels. Refresh retains the selected panel if it
still exists; changing projects resets it. The browser uses one response for all
these views and never downloads the paginated document register for analytics.

## Metric definitions

- The status chart derives **Delayed** from an unissued document whose UBM target
  is before today and which has no delivery date. This does not change stored
  workflow status or the existing `status_counts` contract.
- Burndown lines count remaining documents against UBM target dates and actual
  UBM delivery dates. Future delivery dates do not count as actual deliveries.
  Documents with no delivery evidence remain outstanding, including unknown status.
- **Scheduled** is the proportion with a target on or before today; **Issued**
  uses deliveries on or before today; **Authority approved** uses current status.
- Pending days accumulate workflow intervals: updates belong to UBM, airworthiness
  review and re-submission to AW, and authority review to Authority. An unissued
  document's current overdue target contributes to UBM. Future time is excluded;
  backwards event intervals are reported and skipped without rewriting history.
- Overdue actions use `next_action_due_date`, independently of the UBM target.

Risk policy v1 retains the main-branch thresholds and explainable signals: overdue
targets, long waits, re-submission cycles, missing technical references and authority
aging. Scores are capped at 100; high starts at 60 and medium at 30. The response
includes the 25 highest priorities per scope, with deterministic ordering and full
aggregate counts. Opening a priority uses its document ID. Private document bodies,
paths, recipients and actor details are not included.

Workflow events are prefetched in batches of 500 documents, preventing queries per
document. Timeline size grows with distinct milestone dates and panel counts; each
scope's risk list stays capped at 25. There is no new database schema or dependency.

Regression coverage lives in `compliance.test_dashboard`, `compliance.test_risk`,
`compdocDashboard.test.ts` and `ComplianceDashboard.ui.test.ts`.
