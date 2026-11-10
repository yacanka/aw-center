# Startup storage recovery implementation plan

> **For agentic workers:** Use superpowers:executing-plans inline with test-first implementation and one final independent review. Preserve the user's existing workspace and untracked files.

**Goal:** Recover current-user Windows ACL inheritance safely before startup and detect storage failures before expensive preparation.

**Architecture:** Extend the existing native permission helper, private-directory/lock primitives and Manager admission. Keep inspection and persisted application content strict.

**Tech Stack:** CPython 3.11 standard library, Win32 security APIs, existing unittest/launcher.

**Spec:** `docs/superpowers/specs/2026-11-09-startup-storage-recovery-design.md`

## Global Constraints

- Work in the existing feature branch; leave unrelated `artifacts/` and `tools/` untouched. No commit, publication or deployment is needed for review.
- Recover only unprotected, current-user-owned ACLs. Never take ownership, bypass NTFS/link checks or repair persisted profile/env/database content.
- Preserve real lock contention, cancellation, offline/corporate source boundaries and read-only inspection.
- The user requested proactive implementation; proceed without an additional design/permission round.

## Review Focus

- Another owner or substituted reparse/hard-link target must not be modified.
- A protected unexpected ACL or failed repair must remain a visible error.
- Interrupted or concurrent directory creation must not leave insecure ancestors.
- Preflight must precede automatic source/profile reads and leave no probe files.
- Restart/inspection must preserve existing configuration and read-only behavior.

### Task 1: Ownership-safe native permission recovery

**Files:** `scripts/launcher/installation_permissions.py`, `scripts/test_launcher_permissions.py`.

- [x] Add failing portable native-API regressions for inherited directory/lock-file recovery, read-only verification, ownership/protected-ACL/link/API failure boundaries and post-repair verification.
- [x] Implement `prepare_private(path: Path) -> bool`; use stable file handles and DACL-only recovery, then retain complete owner/ACE verification.
- [x] Run `python -m unittest scripts.test_launcher_permissions` (all pass).

### Task 2: Proactive storage admission and safe directory creation

**Files:** `scripts/launcher/installation_state.py`, `scripts/launcher/resource_locks.py`, `scripts/manager/operations.py`, storage/Manager regression tests.

- [x] Write failing nested-directory, concurrent-creation, inherited-lock and startup-before-profile/write-probe regressions.
- [x] Secure each newly created ancestor, revalidate races, prepare only managed directory/lock ACLs and probe storage with isolated temporary files before Manager mutable actions.
- [x] Run focused storage, locks, preferences, ensure, source and preparation tests (all pass).

### Task 3: Native coverage, documentation and verification

**Files:** `scripts/test_launcher_windows_smoke.py`, `docs/windows-manager.md`, this execution record.

- [x] Cover real inherited NTFS ACL recovery and preserved content/strict read-only checks in the native suite.
- [x] Document automatic recovery limits and retry behavior.
- [x] Run launcher/Manager suites, relevant repository checks and final independent review; report native-only gaps honestly.

## Execution record

- Baseline: 34 focused tests passed with local loopback socket access. The sandbox-only run failed the existing automatic-port test because socket.bind is denied; an isolated bind probe confirmed this environment restriction.
- Task 1: RED/GREEN native-boundary tests passed. Stable handles recheck object type/reparse status and owner before DACL-only inheritance recovery. Directory MAXIMUM_ALLOWED follows Microsoft's documented suppression of recursive SetSecurityInfo propagation; files use exact access rights compatible with live lock streams.
- Task 2: RED/GREEN startup and filesystem regressions passed; 80 focused tests passed before the shared profile-directory case was added.
- Ruling: reuse private_directory for provisioning's duplicate directory creator as well — otherwise an inherited state directory or concurrent mkdir would still block later in setup. Persisted profile/env files remain strictly read-only verified.
- Ruling: the background inspection previously converted inherited-ACL errors to doctor-only blockers. Allow only storage_acl_inheritance through the existing recoverable-error UI path so explicit ensure can attempt narrow recovery; data files still fail strict validation. RED/GREEN controller regressions cover this.
- Final review: one independent read-only reviewer found three Important issues; no Critical/Minor issues. An exclusive-lock native test read was moved after lease release.
- Final: fixed existing intermediate ancestors — explicit root boundary is passed by nested state/profile/cache/runtime/release callers. Existing unsafe ancestors fail before descendant creation; inherited Windows intermediates recover. RED/GREEN regressions passed.
- Final: fixed pre-write owner/hard-link checks and lock identity — ownership is checked before all native security writes, new lock creation is exclusive, volume/file IDs are compared with the retained descriptor, and existing locks never receive owner writes. Elevated default-owner initialization compatibility has its own regression.
- Final: fixed ancestor-junction substitution — normalized final handle path is compared against the lexical DOS long path before any ACL mutation; portable RED/GREEN and native substitution regressions were added.
- Ruling: concurrent unrelated package-source files arrived during verification. Leave those edits untouched. The initial broad launcher run saw eight failures exclusively in those arriving tests; the subsequent coherent run passed 510 tests with 15 skips. Manager run passed 334 tests with eight skips. Full repository backend/frontend test gate, check, prod help, frontend build/budget and isolated collectstatic/artifact verification passed before final security fixes; affected suites are rerun afterward.
- Final verification after fixes: launcher discovery 520 tests / 16 skipped, Manager discovery 334 / eight skipped, core launcher/jobs/release gate 62 passed. No failures. Full repository test command passed (1,414 backend tests, core gate and frontend test:ci). Repository check, frontend build/budget, isolated collectstatic/artifact verification, prod help, compileall and git diff --check passed.
- Native limitation: no Windows executable was built or run on this macOS host. Real NTFS inheritance/identity/LockFileEx/junction tests were added to the existing Windows suites; native Windows acceptance remains required.
- Review dispositions: all three Important findings fixed with RED/GREEN regressions; no deferred Minor findings. Persisted data ACL recovery remains excluded because tightening exposed data does not establish its integrity; concurrent unrelated source changes remain owned by their existing author.
