# Review findings 6–13 implementation plan

> **For agentic workers:** Execute independent frontend, compliance, DDF/comparison and executor lifecycle scopes in parallel; integrate and verify in this session.

**Goal:** Close the selected review findings while preserving current project scope, audit/history, authentication and job fencing guarantees.

**Architecture:** Extend current feature APIs, import services and isolated executor lifecycle. No new framework, dependency or model/migration is planned. Work in the current checkout to retain the user's ongoing JIRA relocation and content separation changes.

**Tech Stack:** Django/DRF, CPython 3.11 production, Vue/Pinia/Axios, existing Vitest/Playwright tests.

**Spec:** The user's selected review findings 6–13 and current AGENTS.md.

## Constraints and review focus

- Preserve all existing edits, migrated JIRA paths and immutable migration history.
- Keep server-side session/CSRF, safe errors, owner/project scope, version/fingerprint checks, import audit/history and worker lease/token fences.
- Bound import/comparison input before materialization; reject invalid shapes with safe validation errors.
- Cover requests completing after disposal, concurrent changes during import, audit persistence failure, malformed document structures and nested process cleanup.
- Do not commit, reset, deploy or change unrelated date-sensitive compliance tests.

## Implementation scopes

- [x] Findings 6/8/9: align person import result and awaited forced refresh; dispose HTTP signal listeners after success/error/cancellation; fence DCC/ECR polling after unmount and selection changes. Tests use real HTTP lifecycle and deferred component responses.
- [x] Findings 7/13: make audit completion atomic with imported documents; bounded single selected-sheet parsing before project lock; batch identity validation/hydration. Prove rollback, partial results, query scaling and stale project fingerprints.
- [x] Findings 11/12: validate DDF table/cell structure and merged cell identity; validate legacy comparison request fields and resource bounds; classify unexpected failures as server errors.
- [x] Finding 10: give each executor ownership of its process tree before any feature code runs. POSIX process session/group, Windows parent-owned Job Object with kill-on-close and startup gate. Test real nested processes on timeout/cancellation/crash and cleanup failure.
- [x] Integrate: inspect all diffs, run focused and complete backend/frontend gates, launcher tests and applicable E2E/build/artifact checks. Report every failure/skip and unrun Windows/PostgreSQL/live integrations.

## Verification result

- Selected backend regressions: 117 passed, including sparse far-row rejection with truthful/forged dimensions and both header-position boundaries; frontend test:ci: 344 unit + 29 compdoc + 74 Node tests passed (447 total).
- Full backend, final source: 1,142 tests, 1,139 passed, 2 skipped, 1 unrelated date-sensitive compliance filter test failed. A previous attempt was interrupted by temporary disk exhaustion; the standalone rerun completed.
- Chromium E2E: 86 passed, 5 failed. Four unchanged session-theme tests expect a removed login `.heading-dot`; the unrelated Excel subtask test expects old `Enter Url` placeholder instead of current `Enter Jira task URL or key`.
- Launcher: 41 passed. Typecheck, formatting, Django check, frontend build/bundle budget, collectstatic and artifact verification passed.
- Independent final review: no blocking findings. Scanner benchmark 200k empty rows peak 16.50 MB -> 0.64 MB.
- Actual Windows/Python 3.11, PostgreSQL locking and live integrations were not run locally. Abrupt import process exit may leave a processing audit; successful/partial evidence is now atomic with its business changes.
