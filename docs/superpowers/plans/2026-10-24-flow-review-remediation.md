# Application flow review remediation

**Goal:** Resolve all thirteen findings from the repository review, preserve existing functionality, and add regression coverage for each.

**Architecture:** Preserve the Django/Vue modular monolith, server-side session/CSRF, owner/project scope, optimistic versions, durable jobs and external-write reconciliation. Correct state transitions and request ownership at their existing boundaries; add no dependency or framework.

**Spec:** The thirteen findings and behavioral impact table in this conversation; root `AGENTS.md`. Implementation is explicitly authorized. No commit, deployment, real provider writes or live database mutation is requested.

## Constraints and review focus

- Preserve all pre-existing dirty changes; do not reset or rewrite migrations.
- Use test-first regression cases with synthetic data and disposable databases/artifacts.
- Distinguish uncertain HTTP delivery from a confirmed terminal job and an explicitly new operation.
- Preserve external-write uncertainty through cancellation, connector failure and worker projection.
- Fence asynchronous UI actions against changed selections, input and unmount.
- Keep audit records and accurately expose their dates, pagination and protected-delete constraints.
- Verify process cleanup with actual descendants as well as platform-specific unit contracts.

## Tasks

- [x] **JIRA/ECR (1, 2, 3).** Test lost enqueue responses for manual/Excel subtasks and stable attempt keys; pass caller-owned keys through `jiraSubtasks.ts` and its page/composable consumers. Test ECR reconciliation cancellation/prerequisite failures and retain uncertainty until a definitive marker result. Test draft reconciliation with failed create preflight; expose a read-only reconciliation action without weakening ordinary publish validation. Owners: integration API/composables/panels and `backend/automations/ecr_*`.
- [x] **Users (4, 9, 10).** Test successful password reset returns to login without refresh; clear reactive reset capability on completion. Test duplicate email through administration and preserve unchanged/blank semantics; enforce the existing email identity policy across relevant admin paths and avoid arbitrary recovery for ambiguous legacy accounts. Test protected user deletion; retain audit FKs and return a sanitized conflict with deactivation guidance. Owners: `backend/users/` and frontend session/login components.
- [x] **Compliance (5, 6, 11, 12).** Test polling failures/cancelled number allocation recovery; expose reload/retry and preserve allocation identity. Test document number/issue changes invalidate/recompute DocProof evidence, including import paths. Test separate review request/decision activity dates. Test pagination of more than fifty reviews and access to old pending tasks. Owners: `backend/compliance/`, frontend compliance API/editor/review UI.
- [x] **Common job and comparison (7, 8).** Add deferred cancel-response regression tests to `usePageJob.test.ts` before fencing actions by revision and identity. Add terminal failed/cancelled comparison retry tests and uncertain-HTTP replay test to `useComparison.test.ts`; release the logical request key after acknowledgement, preserving it across unknown outcomes.
- [x] **Launcher (13).** Add a real descendant cleanup regression plus platform contract tests in launcher tests. Manage launcher-owned process trees on POSIX/Windows while preserving executor containment and orderly termination. Test startup failure and child exit cleanup; do not signal unrelated process groups.
- [x] **Integration verification.** Run focused tests first, then full backend/frontend suites, launcher/release tests, check/type/format, build and isolated static/artifact verification where applicable. Independently review changes against the thirteen scenarios. Record actual commands/results and platform limitations below.

## Validation record

Verified on 24.10.2026 (Europe/Istanbul), using synthetic configuration and disposable SQLite databases.

| Command / gate | Final result |
| --- | --- |
| `.venv/bin/python launcher.py test` | PASS: 1,341 backend tests, 54 launcher/release tests, all frontend CI gates |
| `npm --prefix frontend run test:ci` | PASS: 477 source unit tests, 29 import tests, 73 Node contract tests |
| `.venv/bin/python launcher.py check` | PASS: Django check, no pending model changes, isolated migration plan, full format and type checks |
| `.venv/bin/python launcher.py prod --help` | PASS |
| `npm --prefix frontend run build` | PASS, including bundle budget and postbuild verification |
| Temporary SQLite: `migrate --noinput`, `migrate --check`, `check_project_registry` | PASS; production/local application databases untouched |
| Temporary static root: `collectstatic --clear --noinput`, `verify_frontend_artifact` | PASS: 297 copied files, 42 verified assets |
| `npm --prefix frontend run test:e2e` | 129/130 PASS; dark mobile compliance settings hit the existing 30-second test timeout |
| `npm --prefix frontend run test:e2e -- e2e/compdoc-settings.spec.ts --workers=1` | PASS: all 4 settings scenarios, including the timed-out case (7.2 seconds on retry) |
| `git diff --check` and changed contract-script Prettier | PASS |

Full suite logs: `/tmp/awcenter-oct24-review/full-test.log`, `frontend-ci.log`,
`launcher-check.log`, `frontend-build.log`, `artifact-check.log`, `e2e.log`,
`e2e-settings-retry.log`. These are local verification artifacts, not repository source.

Regression tests were run RED before fixes, then GREEN. Final review additionally
reproduced and fixed macOS unreaped-leader cleanup and Windows broken gate-pipe
cleanup. The existing subtask static contract test was updated to assert the new
caller-owned key instead of the obsolete one-argument resume signature. No
assertions were removed or timeouts relaxed. Local socket/process inspection was
initially sandbox-blocked; approved reruns completed successfully.

## Finding-to-regression map

| # | Corrected behavior | Regression evidence |
| --- | --- | --- |
| 1 | Manual/Excel/resume subtask attempts retain their caller-owned idempotency key across unknown HTTP outcomes; changed input or an accepted attempt gets a fresh key. | `useSubtaskProgress.test.ts`, `test_subtask_jobs.py` (same-key replay produces one job/provider write) |
| 2 | Cancelled or interrupted ECR reconciliation retains uncertainty until a completed marker lookup resolves it. | `automations/test_ecr_workflow.py` (cancel, startup/input/connector/role/session errors, no create/attachment on retry) |
| 3 | A separate read-only draft reconciliation action is available without create-preflight readiness. Ordinary publication validation remains required. | `useJiraIssueDraft.test.ts` (composable and rendered panel) |
| 4 | Successful password recovery clears reactive reset capability and shows login immediately; failed recovery retains retry state. | `session/tests/loginRecovery.test.ts` |
| 5 | Number allocation polling failure exposes recovery; retries reload the existing allocation before resuming. Cancelled attempts are resumable and late replies cannot update another editor. | `compliance/composables/editor.test.ts`, `test_numbering.py` |
| 6 | Number changes clear DocProof evidence; revision changes recompute cached status. Identity changes advance the tracking fence and stale in-flight lookups are rejected, including imports. | `compliance/test_tracking_evidence.py` |
| 7 | A confirmed failed/cancelled comparison can start with a fresh key; unknown enqueue outcomes reuse their key. | `useComparison.test.ts` |
| 8 | Cancel/download replies cannot overwrite a newly selected job or update a disposed page. | `usePageJob.test.ts` |
| 9 | API/admin reject newly introduced nonblank email collisions; ambiguous legacy recovery stays neutral and sends nothing. Blank and unchanged legacy admin identities remain editable. | `users/test_account_flows.py` |
| 10 | Protected audit records prevent deletion with a sanitized 409 and deactivation guidance. | `users/test_account_flows.py` |
| 11 | Review request and decision appear as separate chronological activities. Recent decisions on older requests are included. | `compliance/test_review_activity.py` |
| 12 | Review tasks are paginated in the UI; older pending tasks remain reachable and actionable. | `CompDocReviewPanel.test.ts`, `test_review_activity.py` |
| 13 | Launcher owns POSIX groups / gated Windows Job Objects; cleanup includes descendants and unreaped leaders. Worker shutdown closes detached executor trees and preserves external-write uncertainty. | `scripts/test_launcher_jobs.py`, `jobs/tests/test_isolated_worker.py` |

## Design and compatibility notes

- No schema, dependency, public API route, authentication or authorization policy migration.
- Existing working-tree changes were preserved. No commit, deployment or live provider write.
- Windows containment uses a stdlib-only bootstrap because launcher setup precedes Django dependencies. Commands cannot start before Job Object assignment.
- POSIX cleanup grants workers a bounded 30-second grace period, then kills remaining owned group members. Local interrupted jobs are retryable; potentially external writes require reconciliation.
- A time-of-day-dependent existing filter test was corrected to use `timezone.localdate`, matching the documented Istanbul presentation/filter contract.

## Remaining verification and compatibility limits

- This host is macOS with Python 3.14. Native Windows Job Object / .cmd / DOORS and production CPython 3.11 execution cannot be established by the local tests.
- SQLite is tested; PostgreSQL execution and real JIRA/Numarator/DocProof integrations are not exercised.
- Email validation does not add a database uniqueness constraint. Concurrent independent writes or out-of-band database changes can still introduce collisions; recovery fails closed on ambiguity.
- Existing notification deduplication uses tracking profile + event + revision evidence (`compliance/notifications.py`). Changing the technical number then seeing a previously notified revision can suppress the new notification. This policy is unchanged to avoid a blanket resend on deployment; any change needs a migration-aware design.

