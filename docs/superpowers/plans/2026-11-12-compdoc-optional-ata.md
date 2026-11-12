# Optional CompDoc ATA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Import and edit named panels without ATA while allowing individual documents to acquire different chapters later.

**Architecture:** Keep `orgs.Panel` and the existing compliance foreign key. Empty ATA panels use a private normalized-name identity; populated panels keep their existing ATA identity. Preview stays read-only and confirmation applies reviewed changes atomically.

**Tech Stack:** CPython 3.11.x, Django/DRF, Vue 3, Naive UI, Vitest.

**Spec:** `docs/superpowers/specs/2026-11-12-compdoc-optional-ata-design.md`

## Global Constraints

- CPython 3.11.x; no new dependencies, public routes, or migration rewrites.
- Preserve project scope, document CAS, import confirmation, tracking recipients, audit, and transaction boundaries.
- Preserve the existing shared theme and responsive controls.
- Apply changes in the requested checkout; no commits or branch operations requested.

## Review Focus

- Repeated Unicode names must not create duplicate ATA-less panels.
- Different empty-ATA names must survive import and catalog lookups independently.
- ATA assignment to one document must not change its siblings.
- Missing columns must preserve existing data; empty cells must remain distinguishable.
- Existing organization selectors must not identify several blank-ATA panels by the same empty value.

### Task 1: Model and import identity

**Files:** `backend/orgs/models.py`, `backend/orgs/serializers.py`, new `backend/orgs/migrations/0003_*.py`, `backend/compliance/import_panels.py`, `backend/compliance/imports.py`, `backend/compliance/test_imports.py`, `backend/orgs/test_ata.py`.

**Interfaces:** Catalog ATA is a string, possibly empty; panel references expose a composite internal key; reviewed changes retain existing ATA/name fields.

- [x] Add failing tests for blank ATA, normalized-name uniqueness, repeated/mixed panel rows, omitted/blank cells, and preview conflict/rollback.
- [x] Run the tests and confirm failures describe the missing behavior.
- [x] Implement optional ATA, private name key and forward migration; adapt import identity and application without preview writes.
- [x] Run relevant compliance and organization tests.

### Task 2: Document editing and dependent catalog consumers

**Files:** compliance serializer/services/numbering snapshot, export/options, frontend identity fields/payload/notices, organization panel form and responsible selector, adjacent tests.

**Interfaces:** Document writes may supply a panel name when selecting an ATA-less reference; responses continue exposing the actual panel ID/name and nullable ATA.

- [x] Add failing tests for independent ATA assignment, name preservation on clearing, export round trips, blank catalog options, and panel-ID responsible filtering.
- [x] Implement name resolution only at transactional save, and preserve that name in numbering snapshots.
- [x] Update selectors to use IDs where ATA is no longer unique, without altering existing ATA filter support.
- [x] Run backend module tests and frontend unit/CI checks.

### Task 3: Verification and review

- [x] Run migration generation check, Django checks, SQLite tests and PostgreSQL migration checks on a disposable database.
- [x] Run frontend formatting, typecheck, CI tests, build, collectstatic and artifact verification.
- [x] Review the complete diff with a fresh reviewer and address material findings.
- [x] Report results and environmental limitations; leave changes uncommitted.

## Verification and implementation notes

- Relevant compliance/organization modules: 295 tests passed initially; after review fixes, 118 focused import/optional-ATA/numbering/organization tests passed. PostgreSQL 14: 19 optional-ATA, normalization and concurrent-import tests passed; `makemigrations --check --dry-run` and `migrate --check` passed. A disposable old-schema database preserved panel IDs, names, ATA and Unicode name keys after forward migration; SQLite preservation was also independently checked by the reviewer.
- Frontend `test:ci` passed, including all 97 unit-test files / 539 tests and the command/API contract suites. Formatting and typecheck passed.
- Chromium: four real form-create/ATA-clear cases passed across light/dark themes and widths 390/1440. Screenshots were visually inspected. Build, bundle budget, collectstatic and frontend artifact verification passed.
- Launcher/release metadata: 66 tests passed.
- Full Django suite: 1462 tests ran, with two failures in unchanged job isolation tests: `test_executor_descendants_stop_before_artifact_publication` and the `success` case of `test_nested_processes_stop_on_timeout_cancellation_crash_and_success`. The nested executor logged `PermissionError` in the full run. Both tests passed together in an isolated rerun. Full-suite success is therefore not claimed. Earlier sandbox-only runs hit process/socket permissions; these were rerun with the necessary execution permissions.
- Subsequent pre-commit full Django rerun: all 1462 tests passed in 136.681 seconds. This supersedes the earlier full-suite limitation above; the earlier transient failures are retained as execution history.
- Ruling: preserve populated ATA normalization, but remove inference from numeric-looking Panel-only cells. This is necessary for the accepted missing-ATA semantics. Export now carries actual panel names and a separate ATA column.
- Ruling: the responsible API helper already receives unwrapped rows; remove its second pagination unwrap so ID filtering can display results.
- Deferred, preexisting behavior: the shared spreadsheet formula-prefix escaping convention is not decoded on import. Formula-looking text does not round-trip byte-for-byte; no shared export-security changes were made.
- No persistent development/shared/production database was migrated. Apply the new forward migration through the normal environment migration workflow. No dependency changes were made. Implementation was initially left uncommitted; the user subsequently authorized commit/push and fast-forward integration of the two newer remote commits.
