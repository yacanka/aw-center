# Compliance dashboard

The Compliance Docs home at `/app/compdocs/home` uses the authenticated,
project-role-protected `GET /api/projects/<slug>/compliance-documents/dashboard/`.
`compliance.dashboard` owns the read-only aggregation of canonical documents and
sequence-ordered `WorkflowEvent` records. Table pagination does not limit analytics.

## Dashboard User

Assign the built-in **Dashboard User** role from the Users screen to open a
dedicated Certification Dashboard workspace at sign-in. Assign each user's
Compliance project roles separately to control which projects and actions they
can access. The workspace includes the project dashboard, Compliance Documents,
and the Doc Analyzer and Cover Page Creator tools linked from the project picker.
The server enforces this scope even when the account has other AW Center roles.
For DOORS imports, a Dashboard User with Compliance edit access can use modules
already mapped to their projects. DocProof lookups use document numbers from
projects the user can read.

## Dashboard response

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

Status, publication-status and CAT distributions show only positive categories in
both the chart arcs and the accompanying lists. Empty publication groups retain
their heading and empty message; an all-zero distribution shows the existing empty
state. The API counts and project status catalog are unchanged.

The **Accumulated pending days** card is temporarily hidden by
`SHOW_PENDING_DAYS` in `CompDocTimelineDashboard.vue` (issue #126). Preserve its
chart code, helpers, tests and backend `pending_days` aggregation/API for future
restoration. Burndown and Flow performance remain visible.

## Metric definitions

- The status chart derives **Delayed** from an unissued document whose current target
  is before today and which has no delivery date. This does not change stored
  workflow status or the existing `status_counts` contract.
- Burndown lines count remaining documents against current target dates and actual
  release dates. Future delivery dates do not count as actual deliveries.
  Documents with no delivery evidence remain outstanding, including unknown status.
- The current target uses the revised target when present, otherwise the original
  target. Both stored target dates and the delivery date are independent fields;
  workflow transition dates are separate audit events.
- **Scheduled** is the proportion with a current target on or before today; **Issued**
  uses deliveries on or before today; **Authority approved** uses current status.
- Pending days accumulate workflow intervals: updates belong to UBM, airworthiness
  review and re-submission to AW, and authority review to Authority. An unissued
  document's current overdue target contributes to UBM. Future time is excluded;
  backwards event intervals are reported and skipped without rewriting history.
- Overdue actions use `next_action_due_date`, independently of the target.

## Risk policy v2 (issue #127)

The effective target is the revised target when present, otherwise the original.
A recorded release date suppresses overdue and approaching-target points,
including when the release date is in the future.

| Signal | Points |
| --- | --- |
| Unreleased, at least three calendar months overdue | 100 |
| Unreleased, overdue by less than three calendar months | 80 |
| Unreleased, target today or before today plus one calendar month | 30 |
| Each missing effective target, raw status, cover page number, panel or ATA | 20 |
| Authority Review, release at least one / two calendar months ago | 20 / 30 |
| Aw Review, release at least 15 days / one calendar month ago | 20 / 30 |

The approaching window includes today and excludes the exact one-month boundary.
Calendar-month thresholds add months to the starting date and clip at month end
(for example, 31.01.2027 plus one month is 28.02.2027). Review aging uses the
release date, never the workflow event date. It adds only the highest applicable
age tier; absent or future release dates add no review-age points. Blank and
`unknown` stored statuses count as missing, even if a chart displays a calculated
status. Custom nonblank statuses are present and have no implicit review semantics.

Independent signals add together and the final score is capped at 100; all reasons
remain visible even when their sum exceeds the cap. Workflow stage age remains
informational and a deterministic sorting tie-breaker. Long waits, re-submission
cycles and missing technical document numbers no longer add points.

| Level | Score | Color |
| --- | --- | --- |
| Very high (`very_high`) | 90–100 | Maroon |
| High (`high`) | 70–89 | Red |
| Medium (`medium`) | 30–69 | Orange |
| Low (`low`) | 0–29 | Blue |

All active documents enter level counts, including zero-score documents in Low.
`at_risk_count` and the bounded priority list include only positive scores. Each
scope retains its top 25, ordered by score descending, workflow stage age
descending, then name and document ID. Signal severity remains independently
`high`, `medium` or `low`. Policy metadata exposes version 2, `very_high_score=90`,
`high_score=70`, `medium_score=30`, `max_score=100` and `priority_limit=25`.
The removed `none`, `long_wait_days` and `authority_aging_days` fields are not
part of v2. Backend and frontend must be deployed together; no schema migration
is required. Opening a priority uses its document ID. Private document bodies,
paths, recipients and actor details are not included.

Workflow events are prefetched in batches of 500 documents, preventing queries per
document. Timeline size grows with distinct milestone dates and panel counts; each
scope's risk list stays capped at 25. The revised target adds one nullable date field
and no dependency.

Regression coverage lives in `compliance.test_dashboard`, `compliance.test_risk`,
`compdocDashboard.test.ts` and `ComplianceDashboard.ui.test.ts`.

## Downloadable Windows viewer

On Certification Dashboard Home, select **Download executable**, enter the full
Windows path of an AW Center SQLite file, and select **EXE indir**. The server
checks the user's Compliance project access and embeds the path in that download.
Only the path travels with the file. Its recipient can see it.

Open the downloaded EXE on Windows x64. It opens the dashboard in the default
browser and keeps a small source-selection window open. If the embedded path is
unavailable, enter the new path or use **Gözat**. A successful replacement is
remembered for that source and Windows user. Closing the native window stops the
viewer and removes its temporary database copy.

A local database is opened read-only. For shared drives and UNC paths such as
`\\fileserver\reports\certification.sqlite3`, publish a **completed, standalone
SQLite backup** by atomically replacing the shared file after backup finishes.
Refresh copies and validates the published backup before switching snapshots.
The timestamp records the successful read. Date-dependent metrics use the current
Istanbul date. The local dashboard shows all enabled Certification projects
accessible in the selected file. Windows file and share permissions control
access to the full database, including content outside the viewer.

An administrator may set `AWCENTER_DASHBOARD_SHARES` to newline-separated
`\\server\share` roots in the AW Center process environment. These published
locations open automatically. On first use of another network location the
recipient confirms the displayed destination before Windows connects to it.

### Building the download template

Build from one checkout on Windows x64 with CPython 3.11, in an isolated
packaging environment. Use the repository's existing PyInstaller build pin.

```powershell
npm ci --prefix frontend
npm --prefix frontend run build:viewer
py -3.11 -m venv .cache/viewer-build-env
.cache/viewer-build-env/Scripts/python -m pip install -r packaging/manager-requirements.txt
.cache/viewer-build-env/Scripts/python scripts/build_certification_viewer.py
.cache/viewer-build-env/Scripts/python scripts/verify_certification_exe.py
```

The Certification Dashboard Windows workflow produces the same template. For a
source deployment, install the matching revision's template at
`packaging/dist/CertificationDashboard.exe` under the AW Center installation.
This is a private build artifact served by the authenticated download endpoint.
Publish only the original marked template. The current format produces
unsigned, personalized executables. Sites that require Authenticode signatures
on every executable need a signing stage **after** personalization.
