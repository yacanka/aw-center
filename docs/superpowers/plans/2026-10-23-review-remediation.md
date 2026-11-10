# Repository review remediation

> **For agentic workers:** Implement the independently scoped tasks below with test-first regression coverage. The user authorized all twelve review fixes; no additional implementation approval is pending.

**Goal:** Fix all twelve confirmed review findings while preserving the existing Django/Vue architecture and public API contracts.

**Architecture:** Keep authorization at every exposed entry point, preserve uncertainty through the durable job lifecycle, and bind asynchronous results and review decisions to their source versions. Use existing transaction, process supervision, and test infrastructure; add no dependency or generic framework.

**Tech Stack:** Django, Python 3.11 target, Vue/TypeScript, unittest and Vitest.

**Spec:** The twelve findings in the preceding repository review and root `AGENTS.md`.

## Global constraints

- Preserve session/CSRF, project ownership, job leases, cancellation, fencing and artifact integrity.
- Do not reset databases, edit migration history, remove pending-days code, or modify unrelated source.
- Use temporary test databases and synthetic data. Do not read or print real credentials.
- Keep the working branch; do not commit or publish changes as part of this task.

## Review focus

- A delegated administrator must not gain privileges via admin forms or password endpoints.
- Unknown provider outcomes must remain reconciliation-required after worker terminal projection.
- A shared cover change must invalidate reviews of every affected document without lock-order races.
- Late frontend responses must not change a newer selection or restart disposed polling.
- Startup/timeout failures must release processes and scratch files without deleting active executions.

## Tasks

- [x] **Users and compliance (findings 1, 3, 9).** Modify `backend/users/admin.py`, password serializers/policy and their tests; enforce the documented delegated-admin boundary at Django admin endpoints. Align password acceptance at 128 characters without changing whitespace semantics unexpectedly. Modify compliance cover/review services and tests to reject old evidence after a shared cover revision; prefer existing document version/history rules over a schema change. First demonstrate privilege escalation, two-document stale approval and 128/129 password boundaries in failing tests, then implement and run users/compliance suites.
- [x] **JIRA and job lifecycle (findings 2, 7, 8).** Modify JIRA publication executor/projection, presentation enqueue transaction and job scratch ownership/retention plus their tests. Exercise provider timeout through the worker, early presentation claim, and real child timeout/cancellation. Preserve reconciliation state, atomically associate presentation jobs, and give the parent ownership of execution scratch cleanup including crash orphans. Verify job, JIRA publication, presentation and isolated-worker tests.
- [x] **Frontend state (findings 6, 10, 11).** Modify `useJiraIssueDraft.ts`, `JobCenter.vue`, `compliance/composables/editor.ts` and adjacent tests. Reproduce late draft load/mutation, unmount during polling and stale cover CAS. Fence asynchronous state by selection/lifecycle and update the matching cover version during conflict reload. Run targeted Vitest, complete `test:ci`, format and type checks.
- [x] **Launcher and deployment (findings 4, 5, 12).** Modify launcher TLS validation/bootstrap and process startup cleanup, production checks and related tests. Run CLI with site packages disabled, inject partial startup failure, and reject DEBUG in explicit production modes. Keep TLS validation in the configured project interpreter and clean up every started child on startup failure. Run launcher/release and deployment tests.
- [x] **Integrated validation.** Inspect all diffs and confirm each of the twelve findings has behavior-level regression coverage. Run repository backend/frontend checks, full suites where feasible, frontend build/collectstatic/artifact verification and production CLI help. Document platform-specific validation gaps and any unrelated failures honestly.

## Verification commands

From the repository root: `.venv/bin/python launcher.py check`, `.venv/bin/python launcher.py test`, `.venv/bin/python launcher.py prod --help`, `npm --prefix frontend run build`.

Backend artifact gates: `../.venv/bin/python manage.py collectstatic --clear --noinput` and `../.venv/bin/python manage.py verify_frontend_artifact` from `backend/`, with isolated output locations. Existing production/development state must not be mutated.

## Verification record

- Launcher/deployment: CLI bootstrap and partial startup tests failed before the changes; explicit production DEBUG test failed in both modes. After fixes, 46 launcher/release tests and 27 production/deployment tests passed. TLS is verified through the project interpreter even when the parent runs with `-S`.
- Adjacent correction authorized during implementation: the existing Django admin add form used `UserCreationForm` while its fieldset requires `AdminUserCreationForm.usable_password`. Correct that base on the changed admin/password boundary so valid superuser account creation remains supported.

- Users/compliance: 17 focused regression tests and the complete 343-test app scope passed. Preserve authorized read/autocomplete access while blocking auth-model writes by delegated staff. No schema or migration change. The valid admin-create regression also required standard formset audit bookkeeping via `save(commit=False)`; preference writes still use the existing service.
- Frontend: 16 regressions first failed; the completed focused suite has 30 passing tests. Complete `test:ci` passed with 442 unit tests, 29 import tests and all script gates. Type checking and formatting passed.
- Integrated checks: `launcher.py check` passed. Build and bundle budget passed; isolated `collectstatic` copied 297 files and `verify_frontend_artifact` verified 42 assets. Production help and Python 3.11 `-S` setup help passed. The final full launcher test run and Chromium E2E passed; details follow.

- Integrated regression caught an import cycle between compliance serializers/services. Shared review invalidation moved into `compliance/review_invalidation.py`; architecture and shared-cover tests passed (14 tests), with no architecture-test exception added.
- Final `launcher.py test` passed: 1,308 backend tests, 46 launcher/release tests, 446 frontend unit tests, 29 import tests and every frontend script gate. The initial isolated run had one real import-cycle failure, missing synthetic JIRA URL, and sandbox-denied socket/process inspection. The cycle was fixed; the successful run used `JIRA_URL=https://jira.example.invalid`, a temporary database and authorized local process/socket access.
- Chromium E2E: 130 tests passed. The subsequent editor lifecycle fence passed four new RED-to-GREEN regressions (15 editor tests total), final type/format checks, the full 446-test unit run and rebuilt artifact gates. No UI styling or theme change.
- Jobs/JIRA/PPTX: latest owned suite passed 255 tests. The final reconciliation cancellation/startup projection and concurrent reconversion additions passed all 22 affected tests after the complete run had started. A confirmed absent marker permits a fresh publication; cancelled/failed reconciliation without that evidence does not. Job cancellation itself stays cancelled.
- Scratch cleanup covers success, timeout, cancellation, crash and startup/allocation failure; retention preserves active tokens and rejects symlinks/unrecognized paths. An intermediate macOS nested-process PermissionError did not recur in the instrumented rerun, the 255-test owned run, or the final 1,308-test full run. No exception suppression or test skipping was added.
- Final build, bundle budget, isolated collectstatic (297 files) and frontend artifact verification (42 assets) passed. `git diff --check` passed. No dependencies or migrations changed; no commit or deployment performed.
- Platform limits: full application suites ran on macOS with local Python 3.14 and SQLite. Python 3.11 stdlib-only launcher help was checked, but the complete application suite on Python 3.11, native Windows production/DOORS and PostgreSQL were not executed here. Historical OS-temp files from earlier versions are not deleted by the new owned scratch cleanup.
- Independent final cross-review: no remaining concrete P1/P2 findings. Reviewer independently reran queued reconciliation cancellation and concurrent reconversion successfully; frontend async fixes were also cross-reviewed.
