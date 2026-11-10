# Jira Watcher restoration

Goal: restore the Watcher workflows from `6daa1c6`, preserving current architecture.

Evidence: `60c0974` removed the backend flows and `cbaec72` replaced the
Watcher with a minimal register; `8cb53ff`
restored reminders only. The historical reminder was user-triggered, with
recipients automatically resolved from open subtasks. ECR creation now lives
in the reviewed ECR workflow, and local filesystem probing is intentionally
excluded by the current record contract.

- [x] Add regression tests for URL import, duplicate prevention, project/subject
  authorization, status projection, failures and server-side filters.
- [x] Restore import and live status endpoints under canonical records routes.
  Use server-owned Jira sessions, bounded allowlisted response fields, current
  project resolution and role checks. Preserve optimistic record mutations.
- [x] Restore PDF assessment with the bounded ECR parser and existing configured
  assessment adapter; test upload validation, access and safe errors.
- [x] Restore Watcher actions, expanded subtasks, filters, edit and remove,
  assessment dialog and navigation to reviewed ECR creation. Retain outbox mail.
- [x] Run backend DCC/integration tests, frontend tests/typecheck/format/build,
  static collection and artifact verification. Document live-service limits.

No new dependencies, migrations, credentials, legacy routes or raw Jira payloads.

Implementation also restores automatic Watcher registration on confirmed ECR
publication, preserves existing tracked records, and corrects pagination metadata.
JIRA connector key parsing now retains digits and underscores without truncation.

Verification: DCC, ECR workflow and integration suites; frontend test:ci,
typecheck, format, build, collectstatic and verify_frontend_artifact. Browser
coverage exercises light/dark at 390/1440px with mocked integration responses.
Live JIRA, SMTP and AI services are not contacted by these tests. The existing
local virtualenv uses Python 3.14; CPython 3.11 production parity remains a
release-environment check. No database schema changes are required.
