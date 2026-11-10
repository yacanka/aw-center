# Database integrity follow-up

Preserve all existing users, identities, notification logs and delivery identifiers.
No live migration, provider call, email, commit or deployment is part of this task.
Use new forward migrations, synthetic fixtures and disposable databases.

- [x] Enforce new nonblank email identity uniqueness in the database while retaining unchanged legacy duplicate accounts; cover administration, invitations and direct/bulk writes.
- [x] Bind revision notification deduplication to document identity; migrate historical keys without resetting delivery status or causing bulk resend. Serialize materialization against document changes.
- [x] Audit other writes under actual SQLite IMMEDIATE and PostgreSQL transaction contracts. Fix proven stale password-change and organization/group partial-update races.
- [x] Add real independent-connection concurrency tests, data-preserving migration tests and behavior regressions; run focused and full checks.

SQLite atomic transactions already begin IMMEDIATE. Their read/modify/write paths
must not be labelled unsafe solely because select_for_update is a no-op. Existing
CAS/lease fencing remains in place. Any unsupported or untested platform is reported.

## Confirmed races and corrections

| Surface | Confirmed failure | Correction |
| --- | --- | --- |
| Email create/update | Validation-only check lets competing writers claim the same nonblank identity | Users-owned identity reservation primary key and transactional auth-user triggers on SQLite/PostgreSQL |
| Legacy identities | Adding a unique index would fail or require modifying old duplicates | Seed all owner counts without changing any account field; unchanged old duplicates remain, new competing owners fail |
| SQLite conflict policies | OR IGNORE could bypass a nested unique failure; REPLACE could delete an owner without DELETE trigger maintenance | Explicit aborts for identity and account-key conflicts; ordinary user UPDATE remains supported |
| User administration | Stale serializer saves restore newer password/email or resurrect deleted account | Reload and lock the current account inside the write transaction |
| Password change | Two requests authenticated with the old password both succeed and overwrite each other | Re-read active user under lock before validating current password and saving |
| Legacy reset outbox | Old queued email can select an ambiguous legacy identity | Recheck identity at delivery; cancel safely without sending |
| Invitations | Python casefold can change Unicode address bytes (e.g. ß to ss) differently from DB identity policy | Parameterized database LOWER/TRIM shared normalization; existing records untouched |
| Revision alerts | Same revision letter on another document number matches old sent key | Include document number in a second hash; forward-migrate old keys without changing status, Message-ID, leases or timestamps |
| Alert materialization | A previously loaded profile can re-materialize evidence cleared by an overlapping edit | Document-then-profile locking and fresh evidence under transaction; bounded closed-cursor scanning |
| Panel/person/responsibility/group/DDF PATCH | Full model save from a stale instance reverts unrelated newer fields | Fresh locked instance before merging explicit request fields |
| Slide replacement/deletion | Concurrent replacements leave intermediate images; deletion overlap can resurrect the slide | Parent-then-slide locking, commit-delayed obsolete-file removal, rollback cleanup of newly staged files |

## Audit boundaries

Reviewed user preference/content, invitations, reset outbox claims/confirmation,
compliance lifecycle/tracking/review/numbering, durable job claim/progress/result/
recovery, and JIRA mutation fences. Existing IMMEDIATE transactions, fresh row
locks, partial updates and CAS already protect those audited paths where no
separate defect is listed. No speculative framework or public version contract
was introduced.

## Data-preserving rollout

New forward migrations: `users/0002_email_identity_guard` and
`compliance/0004_revision_notification_identity`. Historical migrations are not
rewritten. Deployment must use the normal stopped-writer/worker maintenance
window, backup, migration, then restart all processes together. Do not run old
notification-key code concurrently with migrated keys. No live migration was
performed by this task.

Old revision hashes do not contain the original document number. The migration
conservatively binds existing history to the current number. This preserves
existing suppression and pending delivery identity, rather than treating all
historical events as new. Later number changes have distinct identities.

SQLite auth-user inserts/upserts that collide with an existing ID/username now
fail closed even with IGNORE/REPLACE; this prevents implicit deletion and broken
reservation counts. Normal application account updates remain available. Email
identity uses the database LOWER/TRIM rules, consistently across validation,
recovery, invitation and triggers; SQLite LOWER is ASCII-case-aware, PostgreSQL
follows its configured collation.

## Verification

Full `launcher.py test` passed: 1,378 SQLite backend tests, 54 launcher tests,
477 frontend unit tests, 29 import tests and 73 Node contract tests.
`launcher.py check` passed, including Django checks, migration drift checks,
frontend formatting and type checking. `git diff --check` passed.
Logs: `/tmp/awcenter-concurrency-review/full-test.log` and `check.log`.

Initial PostgreSQL validation was
51 tests (50 passed, one SQLite-specific skip). Expanded final PostgreSQL
migration/check/concurrency run: 62 tests (59 passed, three SQLite-specific skips).
Both runs created a private temporary cluster with TCP disabled and stopped it
in a finally block; no existing database was used. Local server is PostgreSQL
14.23, not the future deployment's PostgreSQL 17.
Final PostgreSQL log: `/tmp/awcenter-concurrency-review/postgres-final.log`.
Fresh migration, `migrate --check` and `makemigrations --check --dry-run` passed.

Focused SQLite: users 133 passed before the final outbox addition; outbox/reset
13 passed; DDF/PPTX/organization 41 passed; notification integrity 21 passed.
Real separate connections and synchronization barriers reproduce competing
writes. Migration fixtures verify preservation of every account field and all
notification fields except the deliberately changed event key.

Limitations: native Windows and CPython 3.11 execution are not verified on this
macOS/Python 3.14 host. SMTP remains at-least-once across an ambiguous network
success or expired lease; stable Message-ID is preserved, and this change does
not claim provider-level exactly-once delivery. No real mail/provider calls.
Browser E2E and frontend build were not repeated for this backend-only follow-up.
All pre-existing workspace changes were retained; no commit was created.
