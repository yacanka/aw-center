# Manager one-click preparation and opening

Approved user choices: local usage by default, one explicit prepare/open action,
automatic migrations after a verified backup, and free-port selection for
automatic ports. Advanced settings remain optional and effective.

## Constraints

- Reuse Tk, isolated Manager workers, launcher locks and installation receipts.
- Opening the window remains read-only. No new service, startup registration,
  automatic release upgrade, dependency or background framework.
- Existing CLI start/provision/migration behavior remains unchanged.
- Existing keys, accounts, databases and migration history are preserved.
- Stop on integrity, ownership, unknown schema, incompatible runtime or source
  identity failures. No generic start-failure-to-provision fallback.
- Do not reset, fake migrations, restore backups automatically, overwrite old
  backups, or kill unrelated listeners.

## Task 1: Verified migration snapshots

Add a focused launcher module and tests. Manager preparation gets a separate
automatic-backup migration policy; CLI retains explicit migration consent.
Under exclusive lifecycle ownership, snapshot SQLite and private media to a new
owner-only directory below installation-home/backups/profile. Use SQLite backup,
integrity verification and hashes. Bind the manifest/receipt to the DB identity,
profile/environment and migration source/plan. Reject unsafe paths, unknown
existing databases, active WAL/writers, changing media and failed verification.
Operations are bounded and cancellable. Keep a durable started/verified/failed
receipt; interrupted incomplete migration must not automatically repeat. Fully
applied interrupted migration can finish after identity and postchecks match.
No secrets are emitted or placed in manifests. Existing private env/keys remain
in place. Empty new DB initialization needs no backup.

## Task 2: Automatic ports and explicit reconfiguration

Add per-port automatic/manual provenance; legacy absent provenance is manual.
Prefer saved/default 8000 and 5173, choose distinct loopback alternatives when
automatic ports conflict. Manual and prod ports remain fixed. Reconfigure stopped
profiles through hash-bound profile/environment journals. Preserve keys and
state; regenerate generated origins/reset/invitation URLs, reject conflicting
custom derived values. Retry confirmed port conflicts at most three times after
full child cleanup; never retry generic failures.

## Task 3: Manager ensure and optional advanced UI

Add Manager-only ensure, state-based start/provision selection and validation
under branch-appropriate leases. Re-admit if the required branch changes; never
upgrade a held shared lease. Preserve parallel ready dev/prod starts. Explicit
advanced config changes must be applied or explained, never ignored. A running
owned profile offers stop/apply/open. Missing admin is requested via private IPC.
Production requires explicit host/TLS. Main UI shows state, one action, progress
and stop; advanced settings start collapsed. Browser opens once after readiness.

## Task 4: Startup settings and packaging

Preserve settings for the same installation/media context. On moved/new media,
avoid blindly applying old machine paths, preserve old settings and restrictive
source policies. Source precedence: explicit input, verified saved profile,
packaged default. Never silently rebind a profile to a newer source release.
Extend internal metadata compatibly and include new modules in source payloads.

## Task 5: Verification and documentation

Run focused regression tests, Manager and launcher suites, repository checks,
production/SQLite/worker tests and frontend build/static verification. Extend
native Windows acceptance for zero-field ensure, restart, ports, cancellation,
backup/migration and advanced persistence. Native EXE, NTFS/ACL, Job Object and
real Windows UI acceptance must be reported separately from macOS evidence.

## Execution record

- Baseline: clean codex/architecture-consolidation checkout; 68 focused tests
  passed during planning. Work stays in this user-provided checkout; no branch,
  worktree, commit or publication is needed to deliver the requested edits.
- Tasks 1–4 implemented: verified migration snapshots and durable receipts,
  automatic/manual port provenance and journaled connection changes, Manager
  ensure orchestration, optional advanced controls and media-context preferences.
- Task 5 implemented in source: regression coverage, native Windows acceptance
  entry points updated to ensure, payload allowlist and user documentation.
  Native Windows execution remains a separate release gate below.
- Independent reviews covered backup integrity/durability, connection recovery,
  lifecycle claims, IPC and effective advanced settings. Review fixes include
  rejecting unsafe ready-schema histories, forwarding cancellation through
  snapshots, durable Windows publication and applying live asset/catalog edits.
  The final review reported no remaining critical or important findings.
- Verification passed: launcher check (Django checks, migration checks,
  formatting and frontend types); Manager suite (282 tests, 7 skips); launcher
  suite (404 tests, 12 skips); final changed-area regression run (140 tests);
  release metadata/ensure/preferences/distribution run (43 tests); frontend
  test:ci; frontend build and size budget; isolated collectstatic and frontend
  artifact verification; compileall and git diff --check. prod --help passed.
- Full launcher test reached 1,397 backend tests but was not green: the existing
  ArchitectureFitnessTests.test_ai_core_does_not_import_features_or_models
  rejects integrations.ai.transport's existing integrations.tls import. Both
  files are unchanged by this work. Nine additional sandbox socket/process
  errors were covered by a successful unrestricted rerun of SMTP timeout,
  isolated-worker and production-check modules (41 tests). The unrelated
  architecture failure was left unchanged and must be reported separately.
- Remaining platform verification: build the Windows EXE/ZIP and run the native
  acceptance suite on Windows, including NTFS/ACL, write-through publication,
  Job Object containment and real packaged UI/lifecycle behavior. macOS tests
  and mocked Windows API tests do not replace that gate. Frontend browser E2E
  was not rerun because no frontend application source changed.
- Follow-up requested by the user: resolved the architecture failure above.
  The rule had classified the framework-independent shared TLS module as a
  business feature after additive trust was introduced. It now admits that
  exact module and audits its imports too; regression fixtures retain the
  direct/indirect business, user-model, jobs and Django boundaries. The targeted
  architecture/AI/TLS run passed 71 tests. launcher check and the full launcher
  test command subsequently passed: 1,401 backend tests, 58 launcher/release
  tests and all frontend test:ci groups. Production TLS behavior is unchanged.
