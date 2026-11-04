# AWC Manager reliable Windows implementation

The approved chat plan is the specification. Keep Tk/ttk, equal dev/prod,
system-first CPython 3.11 x64, Node 22.13+ (22.x) or 24+, npm 10.9.4+ (10.x)/11.x.
Restricted acquisition is verified local → selected → public; corporate remains
selected-only, offline has no network. Full USB media always carries all core
runtimes and dependencies. Optional approved assets are selected explicitly.

## Deliverables

1. Restricted source policy, bounded tool discovery, frozen/source parity.
2. Full verified Manager distribution and portable startup defaults.
3. OS lifecycle/resource locking, TLS preflight, resumable preparation and health.
4. Adaptive profile UI, independent tasks, safe retries and minimize/exit.
5. Native Windows offline dev/prod acceptance, documentation and final review.

## Acceptance

Real Windows tests must cover system/no tools, cold offline dev/prod, actual
session/CSRF/job/private download, cancellation, lock conflicts and restart.
Never claim native Windows validation from macOS. Preserve migration consent,
database/keys/private state, TLS/hash verification and process containment.
No updater, service, tray integration, public HTTP API or dependency upgrade.

## Execution record

- Started from clean `codex/architecture-consolidation`; implement in the existing
  user workspace without changing branches or creating a separate checkout.
- Baseline from planning: 538 tests, 479 passed, 59 skipped on macOS.
- Source policy feeds bundle preparation and UI; profile lifecycle owns health
  and resource claims; UI never performs blocking discovery or acquisition.

## Implementation record — 05.11.2026

1. Source/tool policy implemented in `installation_sources`,
   `installation_dependencies`, `runtime_selection`, `probe_budget`,
   `system_python`, `system_node` and `toolchain`. Restricted mode is distinct
   from corporate; fallback is availability-only, final installs are offline.
   System tools are validated without global writes. Explicit invalid selections
   and indeterminate probes fail visibly. Saved profile interpreter bindings are
   preserved. Node minimum is 22.13; discovery budgets are 120/60 seconds.
2. Full media preparation implemented in `manager.distribution`,
   `installation_bundle`, `build_manager` and portable startup paths. Production
   of an EXE remains native Windows. The isolated producer includes all pinned
   runtimes even when system tools are present, plus wheels, npm cache and
   selected assets. Versioned inventories bind the EXE/internal/source/dependency
   payload. Existing install manifests remain readable. Wheel acquisition also
   covers patch-conditional requirements across Python 3.11 without changing the
   lock, including async-timeout for 3.11.0–3.11.2.
3. OS resource leases now cover GUI and CLI profile/source/runtime writes and
   survive until child cleanup. Prepared stages are reused only after lock and
   installed-file verification. Owned partial venv creation is resumable; unknown
   environments are preserved. TLS preflight precedes private profile/schema
   creation. Windows paths must be local NTFS. Controlled Windows commands use a
   separate startup gate and Job Object while preserving stdin. Health uses the
   existing real HTTP/worker boundaries, every 10 seconds with 3-fail/2-pass
   hysteresis and no automatic restart.
4. The Tk home screen now emphasizes profile state, one primary action and real
   stage/elapsed/wait information. Read-only background inspection rejects stale
   results. Task reports and source checks cannot replace live profile controls.
   Production TLS fields are visible; retry uses the original task snapshot.
   Browser opening is once per successful launch; stopped URLs are cleared.
   Active X minimizes and explicit Exit follows safe process cleanup.
5. Added required native Windows offline acceptance in the package workflow:
   dev/prod × system/managed tools, real Firewall egress denial, HTTPS,
   session/CSRF, frontend, DOCX comparison worker, private downloads, cancel/retry,
   competing Manager/CLI, crash/stop cleanup, and persisted keys/users/artifacts.
   Windows field checks and exact limitations are in `docs/windows-manager.md`.

## Final review and rulings

One independent final reviewer (`final_manager_review`) returned two P2 findings.
Both were accepted and corrected with failing regression tests first:

- Nonzero/malformed npm probes could trigger managed acquisition. They now
  produce explicit failures; only absent or known incompatible npm permits
  acquisition. Existing tests distinguish unsupported versions from bad replies.
- Selecting the canonical production release for preparation could attempt a
  read-to-write upgrade of its own lease. The mutable destination is now claimed
  for writing before entering the nested lifecycle.

The reviewer did not certify native Job Object/LockFileEx/frozen stdio/Firewall
or DPI behavior from macOS. This is an execution limitation, not a waiver of
acceptance. These remain mandatory Windows CI/field gates. No second review loop
was started. A subsequent self-check added the Python patch wheel regression;
all affected suites were rerun after that change.

## Fresh verification

- Launcher discovery: **321 tests, 309 passed, 12 skipped**.
- Manager discovery: **247 tests, 199 passed, 48 skipped**.
- Release metadata: **12 passed**. The 60 discovery skips concern unavailable
  Windows/display or explicitly enabled native integration environments.
- `python launcher.py check`: passed (Django checks, migration consistency,
  frontend formatting and type checks).
- `python launcher.py prod --help`: passed.
- Frontend `test:ci` and build: passed; initial JS budget passed.
- `manage.py collectstatic --noinput` and `verify_frontend_artifact`: passed.
- Python compile check and `git diff --check`: passed.
- Full `launcher.py test`: backend ran **1397 tests**, with 1 existing architecture
  failure and 9 sandbox-related errors; its later stages consequently did not
  run in that command. Frontend and launcher suites were run separately above.
- The affected SMTP/isolated-process module tests were rerun with local process
  and port access outside the sandbox: **23 passed**. The unrelated architecture
  violation `integrations.ai.transport -> integrations.tls` is already present
  in HEAD and was not changed in this task.

## Remaining release evidence

No Windows EXE was built or run on this macOS host. Native Windows CI, a genuinely
clean machine without installed tools, a standard user account, and the real
corporate network must pass before release. Forced managed selection on a CI
machine with system tools is not evidence of a clean host. Verify light/dark,
100/150/200% scaling, small windows, keyboard navigation and minimize/restore on
Windows. Office/DOORS licenses and remote JIRA/SMTP connectivity remain separate
capabilities. No public API, dependency lock, application data, Git history or
system tool installation was changed; no commit/push was requested or made.
