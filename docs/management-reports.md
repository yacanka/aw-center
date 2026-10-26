# Management Reports

Management Reports is a separate application area at `/app/management-reports`,
available from the main menu. Existing Compliance Docs dashboards are unchanged.

## Before first use

Install the updated backend dependencies using the normal setup flow, and apply
the new migration explicitly:

```bash
python launcher.py setup
python launcher.py dev --migrate
```

Setup/check commands do not apply database migrations automatically. The
`management_reports.0001_initial` migration creates the private report snapshot
table. The feature does not modify CompDoc data.

## Capture and compare

1. Open **Management Reports** and select the portfolio projects. The API lists
   only enabled CompDoc projects for which you currently have view permission.
2. Inspect the live executive metrics, project breakdown and risk priorities.
3. Enter a report title and optional management context/decision request, then
   choose **Save current report**. This captures current server data; it does
   not backdate the data or save unsaved edits from other screens.
4. Open a saved report from the paginated history and choose **Download saved
   PDF**. The PDF uses the captured report and the displayed baseline. Long
   notes or priority lists continue onto additional pages.

The default weekly comparison uses the latest report captured in the preceding
Monday-Sunday calendar week, with the same owner, project scope and metric
schema. The server uses the application's configured timezone to define the
week. The view shows the actual capture dates and elapsed time.

If no matching previous-week capture exists, the comparison is unavailable.
Saving reports each week establishes the history; no scheduled captures or
backfilled historical reports are created by this release. An older compatible
saved report may be selected explicitly from the current history page. Browse
history pages to access other saved baselines; clearing the selection restores
the automatic previous-week baseline.

## Interpret the metrics

- Approval is authority-approved documents divided by all active documents in
  scope. Portfolio percentages use document totals, not average project rates.
- Issued follows the existing CompDoc dashboard definition and is distinct from
  authority approval. Review/approval task counts are internal task counts.
- Schedule variance is issued minus scheduled documents at capture time. A
  negative number indicates fewer issued documents than planned; it is not a
  completion-date forecast.
- Comparison values are **net changes in captured stocks**. Scope additions,
  removals or reopened statuses may affect them; they are not counts of events
  that happened between the reports. Approval-rate changes use percentage points.
- Risk scores are explainable policy-based priorities, not probabilities.
  Risk priorities provide evidence for review; management notes can record the
  author's decision requests.
- Data-quality counts count issues; one document may have several issues.
- Capture time is when AW Center calculated the report. It does not establish
  the last synchronization time of JIRA or another external source.

## Privacy and lifecycle

Saved reports belong to the creator. Viewing history, opening a report,
selecting a baseline and downloading PDF all recheck current access to every
project in the report. A report is not partially disclosed after access is
revoked. Sharing, editing and deleting saved reports are not exposed by the API.

Reports are stored as database snapshots. PDF output is generated in memory
and downloaded through an authenticated endpoint; no public media URL is created.

## PDF dependency

ReportLab is the only new direct dependency, used for searchable vector PDFs
with predictable layout. Existing pypdf supports PDF inspection/manipulation,
not the required document composition. ReportLab is BSD licensed; the packaged
Noto Sans fonts use the accompanying SIL Open Font License. No frontend package
or browser network font is added. The installed ReportLab wheel is approximately
1.9 MiB; the two bundled font files total approximately 1.1 MiB.

`requirements.txt` was regenerated with pip-compile under CPython 3.11, retaining
the existing Windows marker dependencies and pins. Cross-compiling from macOS
required Windows marker/wheel-tag resolution; future lock updates should be
generated on the target Windows x64/CPython 3.11 environment to preserve those
entries. No unrelated pinned package version was upgraded.
