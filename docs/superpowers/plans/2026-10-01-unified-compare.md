# Unified Compare Implementation Plan

**Goal:** Implement the approved in-chat unified Compare design: same-family inputs, shared matching presets, guided single-table Excel matching, and DOCX/XLSX output through existing durable jobs.

**Architecture:** A model-free `comparison` feature package owns bounded readers, matching, inspection, reports, packaging, and HTTP orchestration. Existing jobs own scheduling, fencing, artifacts, and cancellation. Existing legacy APIs remain compatible.

**Constraints:** No new dependencies, migrations, public media, browser credentials, generic plugin framework, or job states. Preserve unrelated working tree changes. Use the existing Naive UI theme. Text/cell content only; no OCR, visual or cross-family comparison.

## Tasks
- [x] 1. Tests then bounded shared matching contracts, readers, and Excel inspection. Validate presets, exact-vs-similar distinction, conservation of source content, duplicate/ambiguous rows, formulas, and schema changes.
- [x] 2. Tests then deterministic private input packages, inspection/compare jobs and owner-scoped APIs. Verify integrity, idempotency, retention, cancellation, and sanitized failures.
- [x] 3. Tests then shared DOCX/XLSX reports. Verify real text changes, references, warnings, counts and spreadsheet formula neutralization.
- [x] 4. Tests then unified Naive UI screen, typed feature API/composable, Excel guidance and route/menu integration. Preserve old endpoints; redirect old UI routes. Verify stale requests and one-time automatic download.
- [x] 5. Run backend/worker/security suites, frontend checks and E2E, build and artifact checks; review the whole change and fix findings.

## Implementation decisions
- Two local job kinds: `comparison.inspect` and `comparison.compare`, timeout 900 seconds.
- API: authenticated GET `presets/`; multipart POST `inspections/`; owner-scoped GET `inspections/<uuid>/`; POST `jobs/`. Relative to `/api/tools/compare/`.
- Inspection POST accepts two files or an existing owned inspection ID plus revised Excel selections. Compare POST accepts two Word/PDF files, or a completed Excel inspection ID and its resolved selections.
- Deterministic server-created ZIP holds exactly `manifest.json`, `first`, and `second`; manifest carries validated original names and each payload hash. Never extract client paths.
- Shared result entries separate change (`equal`, `replace`, `insert`, `delete`) from strength (`exact`, `strong`, `possible`, `none`), retain both source locations and full cell/text values.
- Default preset balanced (0.92/0.70); strict 0.98/0.85; revision 0.85/0.55. Custom validates finite 0 < weak <= equal <= 1.
- Initial bounds: 100 sheets, 20 header candidates, 100 columns, 10,000 rows per table, 10,000 text blocks, 1,000 PDF pages, 2,000,000 extracted characters, 2,000 characters per fuzzy candidate, 250,000 candidate pairs. Explicit limit errors, never silent truncation of report data.

## Review focus
Repeated text, nearly identical numbers, duplicate/blank identifiers, changed spreadsheet columns, and stale frontend inspection responses must not lose or falsely equate data.

## Execution ledger
- Approved design and execution are supplied in the conversation; no additional approval checkpoint needed.
- Work in the existing `codex/architecture-consolidation` feature checkout; unrelated modified files remain untouched. No automatic commits.

- Implemented matching/readers, immutable job API, shared reports, and unified UI. Initial 106 backend tests passed (1 environment skip), frontend CI passed, 5 Chromium flow/theme tests passed. Review identified header-exclusion and restored-job races; failing regression tests reproduced both, fixes pass. Further CPython 3.11 verification in progress.

- Complete: final focused comparison/Word suite 41/41 on CPython 3.11; broad backend regression run 119 tests, 118 passed and existing FFmpeg-dependent media test skipped. Latest strength classification change verified by the final focused suite.
- Frontend CI passed (224 unit tests, 28 compliance tests and all script checks); typecheck, format check and build passed. Django check and migration dry-run passed without model changes. collectstatic and verify_frontend_artifact passed.
- Browser verification: initial Compare 5/5 passed across light/dark and mobile/desktop. Expanded session/responsive/Compare run 26/27 passed; one Compare startup overlapped a Vite source reload and failed to navigate. With sources stable, all five Compare cases passed again. All 12 session and 10 responsive cases passed in the expanded run.
- Independent review findings closed: delayed monitor restoration, unconfirmed auto-header exclusions, and worksheet switching implicitly confirming guessed headers. Added failing-then-passing regression tests for each. Excel candidate-limit failures now return guidance, unselected sheets are sampled only, and unexpected nested selection fields are rejected before persistence.
- Runtime follow-up: restart the existing local worker to load comparison.inspect/comparison.compare. No dependency, schema or database migration; no commit, push or deployment performed.
