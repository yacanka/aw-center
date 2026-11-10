# Management reports architecture integration

**Goal:** Preserve local main's reporting feature and commit ancestry, adapt it to
the current architecture, verify the combined tree, then merge and push main.

**Spec:** The user's approved integration request in this chat. Existing snapshot,
weekly comparison and PDF behavior must remain available.

**Architecture:** Keep `management_reports.ReportSnapshot` and its initial
migration intact. Read business data exclusively through canonical compliance
models and dashboard calculations. Use enabled `orgs.Project` records and direct
or group compliance viewer roles. Place frontend code in
`features/management-reports`, with the shared session/CSRF HTTP client.

**Decisions:** Resolve documentation in favor of the current architecture and
retain reporting documentation. Keep the report payload and immutable snapshot
table; publish only `/api/management-reports/`, with no legacy aliases. Retain the
current dependency pins and regenerate the lock with ReportLab included.

## Tasks

- [x] Adapt backend tests first: canonical data, group roles, disabled projects,
  revoked access, owner isolation, CSRF, full catalog, bounded history queries,
  operational counters, rollback and Turkish PDF dates; observe failure.
- [x] Implement canonical reporting access and calculations, keeping snapshot
  persistence and comparison semantics; run reporting and compliance regressions.
- [x] Move frontend reporting into its feature; adapt transport, route/menu,
  stale-response handling and date presentation. Run frontend regression tests,
  typecheck, formatting and browser smoke including light/dark mobile layouts.
- [ ] Verify Django/migrations with disposable SQLite and PostgreSQL, all backend
  and launcher tests, build/static artifact checks, dependency checks, and CI
  including Windows. Obtain an independent review and address blocking findings.
- [ ] Preserve both original histories, merge the verified architecture branch
  into main, push without force, and verify remote refs and CI.

## Review focus

Mixed-project snapshots must remain private after any permission revocation.
Disabled or non-compliance projects cannot enter options/captures. History must
not enumerate the power set of the expanded project catalog. A late options,
history or PDF response cannot restore stale scope data. Dates in UI and PDF use
Europe/Istanbul and dd.MM.yyyy while persisted/API values stay ISO.

## Integration verification

- Django check, migration drift, frontend formatting and TypeScript passed.
- Full Django suite: 1,437 tests passed on the repeated complete run; the first
  run hit one worker fixture PermissionError, whose isolated repeat also passed.
- Launcher/release: 62 tests passed. Explicit PDF and assistant catalog: 25 passed.
- Disposable PostgreSQL 17: fresh migrate, migrate check, drift, registry and
  47 reporting/dashboard/catalog tests passed. Disposable SQLite migration,
  drift and registry checks passed. Existing application databases were untouched.
- Frontend: 533 unit tests plus the complete script/report contract chain passed.
- Browser: 148 tests passed; after the HTTP fix, four reporting flows passed
  again, including expired-session PDF redirects in both themes and viewport sizes.
- Build, temporary collectstatic and artifact verification passed. PDF rendering
  and light/dark report screenshots were visually inspected.
- Independent review found one PDF Blob authentication integration issue. The
  shared HTTP interceptor now decodes bounded JSON 403 bodies before authentication
  detection; interceptor regression tests failed first, then all 24 focused tests
  passed. No other actionable integration findings were reported.
- Security gates remain blocked by preexisting dependency advisories: npm audit
  initially reported 9 high findings; pip-audit reported 108 findings in 13 packages.
  The user subsequently authorized security dependency upgrades, keeping Django
  on 5.2 LTS and all approved NLP pins unchanged.

## Approved security follow-up

- [x] Resolve only vulnerable Python packages and necessary transitives with
  Django `<5.3`, universal Windows/Linux markers and unchanged approved NLP pins.
- [x] Resolve frontend advisories with compatible package updates; use explicit
  manifest changes where a transitive override or older toolchain blocks a fix.
- [ ] Install from regenerated locks; rerun audits, full tests, browser tests,
  type/format/build/static gates and inspect any CI failures at their root cause.
- [ ] Review the security diff independently, push the candidate and wait for all
  CI workflows to pass before merging main. Verify remote/local main afterwards.

## Security and CI corrections

- Python audit now reports no known vulnerabilities. Django is 5.2.19; the eleven
  approved NLP pins are unchanged from 93dfd69. Universal lock generation retains
  platform markers. pypdf stays on 6.x and soupsieve on 2.x to avoid unnecessary
  major upgrades while removing their advisories.
- Frontend audit now reports zero vulnerabilities. Vue stays on 3.5, Vitest on 4;
  vue-tsc is upgraded to its supported 3.x line. Glob/minimatch overrides fix the
  existing development dependency chain. Independent review caught the older
  global brace-expansion override; it was removed so minimatch uses its compatible
  named-export API. Source glob and EditorConfig regressions failed before the
  dependency correction and pass after it.
- PostgreSQL numbering had attempted FOR UPDATE across nullable joins. Locking
  only the allocation retains execution fencing; existing document and cover-page
  locks are still acquired when binding. Existing numbering regressions failed
  on PostgreSQL first, then all 42 numbering/reminder tests passed.
- CI fixtures now explicitly set the synthetic JIRA URL and isolate installation
  environment values; the Windows SQLite probe fixture closes its connection.
  The inherited-environment reproducer failed first and all 16 targeted tests
  passed after correction. Production environment validation is unchanged.
- Spawned worker tests now export the actual PostgreSQL test database name and
  private scratch root, as they already did for SQLite. They never reconnect to
  the source database. All 21 isolated-worker tests pass on PostgreSQL.
- The new typechecker uses an explicit form instance binding. Browser chart tests
  discover the public Chart registry in loaded modules without assuming chunk
  filenames. Saved-list tests await PUT completion before reading stored content;
  the deliberately delayed-save assertions and every expected value remain intact.
