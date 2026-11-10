# Management Reports verification record

Verified on 2026-10-27 against the first-release design.

## Passing checks

- `manage.py test management_reports common.test_compdoc_dashboard`: 24 tests
  pass (18 reporting/PDF tests and 6 existing dashboard regressions).
- `manage.py check`: no issues.
- `manage.py makemigrations --check --dry-run`: no changes detected.
- Launcher unit tests: 14 pass.
- Frontend `format:check`, `typecheck`, `test:ci`, and production `build`: pass.
  Reporting suite: 8 tests, including PDF JSON-Blob errors and request guards.
- Naive UI production bundle budget passes; the existing general Vite warning
  about chunks over 500 kB remains.
- Changed Python source parses with CPython 3.11. Runtime Django tests used the
  repository's installed CPython 3.14 environment.
- Real Playwright browser session against an isolated Django SQLite database:
  authorized project options, live summary, previous-week comparison, report
  capture, history and genuine PDF download pass, without browser runtime errors.
- Desktop 1440px and mobile 390px checked. Report-only compact shell leaves
  navigation available; document viewport/scroll widths are both 390px.
- Representative single-page PDF, genuine browser download and a two-page
  long Turkish-content report rendered with Poppler and visually inspected.
  Text remains searchable and full notes continue without clipping.
- Independent review: JSON-Blob transport P2 fixed and regression tested;
  report-only mobile expand trigger P3 fixed. No remaining P0-P2 findings.
- `git diff --check`: passes.

## Existing failures and deployment action

`python launcher.py test` runs 519 Django tests; 517 pass and these two fail:

1. `common.test_compdoc_import_concurrency.CompdocImportConcurrencyTests.test_existing_target_change_rejects_without_overwrite`
2. `common.test_compdoc_import_concurrency.CompdocImportConcurrencyTests.test_unrelated_document_change_does_not_invalidate_plan`

Both failures were reproduced from the unchanged `HEAD` source extracted into
an independent temporary directory, with a disposable Django test database.
They are existing CompDoc import issues, outside this reporting change.
Because the launcher stops at that failed Django step, launcher unit tests and
the frontend suite were also run separately and pass.

`python launcher.py check` passes system checks and migration drift checks, then
stops at `migrate --check` because `management_reports.0001_initial` has not been
applied to the user's database. This is expected; no user database migration
was executed. Install the updated dependencies and explicitly run the normal
`python launcher.py dev --migrate` flow before using the new screen.

## Deliberate first-release limits

- Reports are owner-scoped and captured manually; no scheduled capture/sharing.
- A missing previous-week capture shows an unavailable comparison. Explicit
  older baselines may be selected, with their actual dates displayed.
- Capture uses existing multi-query dashboard definitions and normal database
  transaction isolation; it does not claim a serializable cross-project read.
- Dependency resolution retained existing pins and Windows marker dependencies.
  ReportLab and its bundled OFL font assets are documented in
  `docs/management-reports.md`.
