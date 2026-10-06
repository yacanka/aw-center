# JIRA Watcher

Restored from the historical implementation at `6daa1c6`. Backend workflows
were removed in `60c0974`; the minimal frontend register was introduced in
`cbaec72`. The implementation uses the current session, project role and mail
outbox contracts instead of restoring retired routes.

- **Add JIRA issue:** enter a key or a browse URL on the configured JIRA host.
  The server resolves the title and every project, requires DCC operator access,
  rejects subtasks, and prevents duplicate watches for the same owner.
- **Check status / Sync:** fetch live task and subtask states. Sync processes
  active records on the displayed page sequentially. Failed checks show an error
  instead of retaining a stale completion badge. Open Details for
  subtask links and ECD/DCC numbers; an unchecked issue is loaded automatically. Jira's done category determines completion;
  workflows without categories fall back to Closed/Done/Resolved.
- **Filter / Edit / Remove:** filter before pagination, change title/activeness,
  or remove the local watch with optimistic version checks. Removing a watch
  does not delete the JIRA issue.
- **Send reminder:** enter CCB number and due date. Open subtask assignees are
  resolved automatically. The existing durable notification outbox handles
  delivery, retry, lease fencing, idempotency and the per-record cooldown.
  As in the historical implementation, enqueueing is user-triggered; there is
  no recurring automatic mail scheduler.
- **Assessment:** choose governed projects and an ECR PDF. The bounded canonical
  ECR parser supplies document data to the configured AI service for the nine
  historical panels. Results are plain-text draft advice for specialist review.
  The browser allows up to 390 seconds for parsing, connecting and assessment.
- **Create from ECR:** opens the current reviewed ECR publication workflow.
  Confirmed publication automatically creates a Watcher record atomically.

JIRA credentials remain in the existing server-side integration session. AI
uses `ASSESSMENT_API_URL`, `ASSESSMENT_API_ALLOWED_HOSTS`,
`ASSESSMENT_API_MODEL_ID` and `ASSESSMENT_API_TOKEN`; mail uses the existing
notification worker and SMTP configuration. No new dependencies or migrations
are required. Browser-provided filesystem paths and legacy raw credential
endpoints remain retired by the current architecture.

Tests use controlled Jira/AI responses and a local SMTP test server, not live
external services. Verify production credentials and connectivity in the normal
release environment. The local test virtualenv is Python 3.14; production's
CPython 3.11 environment should run the same checks before deployment.

Restoration validation (2026-10-05): 339 backend tests passed; frontend `test:ci`
passed (232 source unit tests, 28 import tests and the script suites); all four
Watcher Chromium scenarios passed. Typecheck, format check, production build,
Django system check, static collection and artifact verification passed.
Changed backend modules also passed CPython 3.11 syntax compilation.

UI refinement: desktop rows and compact-screen cards share the same actions.
Details opens a drawer with refresh, document metadata and an outstanding-only
subtask filter. Reminder is a direct action; status checks, edit and removal
are grouped in the accessible More actions menu. Filter reset, empty-result
guidance and retry actions are available without leaving the page. Assessment
results can be copied and are cleared when the selected input changes.

UI verification: seven Chromium scenarios passed, covering light/dark themes at
375px and 1440px, landscape with reduced motion, keyboard interaction, retry,
viewer permissions and in-flight dialog protection. Frontend tests, typecheck,
format check and production build passed.
