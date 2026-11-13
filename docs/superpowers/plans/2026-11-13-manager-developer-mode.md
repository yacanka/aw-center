# Manager Developer Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make repeated development startup fast inside Manager while keeping managed and production integrity gates.

**Architecture:** Carry an explicit `managed`/`developer` validation policy in immutable Manager requests. Only dev startup and automatic inspection use limited checks; preparation and doctor keep full verification. Reuse the existing launcher lifecycle and add a dev-only Mermaid build cache independently.

**Tech Stack:** CPython 3.11.x, Tk, Django, Vue/Vite, Node.js, unittest and Node test runner.

**Spec:** `docs/superpowers/specs/2026-11-13-manager-developer-mode-design.md` (approved for implementation by the user).

## Global Constraints

- Default policy is `managed`; unknown values and `prod` + `developer` are rejected by workers.
- `developer` requires an explicit editable source selection; source changes reset the choice.
- CPython 3.11.x remains the only supported Python minor version.
- Existing private profiles, keys, data separation, lifecycle locks, migration checks, HTTP/worker readiness and process cleanup remain enforced.
- Download/install integrity, source policy, doctor and all production deployment gates remain comprehensive by default.
- A fast result never creates or replaces comprehensive integrity evidence.
- No new dependencies or general-purpose validation framework.
- Windows timings cannot be inferred from Linux tests; retain separate native acceptance evidence.

## Review Focus

- Old settings or malformed worker policy must preserve defaults or reject, never silently select developer.
- A source/profile change or in-flight request must not inherit another context's developer choice.
- Developer metadata caches must invalidate on lock/receipt changes and must not add files to strict package inventories.
- Managed/prod/doctor callers must retain default comprehensive verification after optional arguments are added.
- Concurrent renderer builds, changed inputs, missing/corrupt output and force-rebuild must not authorize stale cache content.

## Execution and ownership

The session is an isolated cloud checkout on branch `work`; use it directly. The user explicitly authorized implementation; do not add an execution approval gate. Independent tasks 1–3 may run concurrently with disjoint file ownership and root-only staging/commits. Task 4 consumes their exact interfaces. Reports and progress live under `/workspace/work/manager-developer/`.

### Task 1: Manager developer selection and policy boundary

**Files:** Create `scripts/launcher/validation_policy.py`; modify `scripts/manager/view_model.py`, `view.py`, `preferences.py`, `paths.py`, `controller.py`, `task_policy.py` as required; add `scripts/test_manager_developer_policy.py`; extend relevant preference/UI/controller tests.

**Interfaces:** Produce `require_validation_policy(value='managed', *, profile='dev', source_selection=None) -> str`, raising `LauncherError` with safe code/field on invalid policy. If `source_selection` is supplied, developer requires `explicit`. Add `validation_policy` to Manager form defaults and request snapshots. Worker argument parsing is owned by Task 4.

- [x] Write failing tests for missing/unknown policy, prod rejection, explicit source selection, preference reload/source-context reset, and a running task retaining its original policy.
- [x] Run the focused new tests and confirm the intended failures.
- [x] Implement the helper, advanced developer selector, visible active-mode indication, source-bound persistence and resetting on source/profile/media context changes. Keep Tk free of filesystem/network work. Existing doctor action is labelled `Tam doğrula` and remains full.
- [x] Run focused policy/preference/controller/view tests. Existing selection/restart comparisons include validation policy. Report RED/GREEN evidence and changed files; root commits only owned files.

### Task 2: Limited runtime and dependency verification

**Files:** Modify `scripts/launcher/installation_dependencies.py`, `toolchain.py`, `installation_features.py`, `installation.py`; create `scripts/launcher/developer_readiness.py` only if a focused small metadata cache needs its own file; add `scripts/test_launcher_developer_validation.py` and extend narrowly related tests.

**Interfaces:** Extend `dependency_checks(project, *, verify=True, fail_invalid=False, developer=False)`; `inspect_toolchain(home, *, python_executable=None, node_executable=None, verify=True)`; `toolchain_environment` with the same `verify=True`; `feature_environment(project, profile, *, verify=True)`; `_core_checks(..., validation_policy='managed')`; `start_profile` and `_start_profile` with keyword `validation_policy='managed'`. Existing callers keep full defaults. Validate policy/profile via Task 1 helper before allowing developer behavior.

- [x] Add failing tests proving developer checks/startup perform no full package/runtime/optional-tool inventory and managed paths still detect modified bytes.
- [x] Cover changed locks, missing receipts/required executables, safe paths, cached metadata invalidation, and unchanged full receipts after fast checks. Store any small metadata outside strict inventory trees and in ignored generated state.
- [x] Implement limited runtime identity/version and executable checks, small dependency readiness metadata (a one-time full receipt parse is allowed), and conditional startup propagation. Automatic inspection gets no backend process from this task; Task 4 owns that behavior.
- [x] Preserve migration/worker/HTTP/cleanup behavior and full preparation/doctor verification. Do not weaken download validation or make all callers pass `verify=False`.
- [x] Run focused tests, then the affected launcher groups. Report exact evidence; root commits only owned files.

### Task 3: Dev-only Mermaid renderer cache

**Files:** Modify `frontend/scripts/build-mermaid-renderer.mjs`, `frontend/package.json`; optionally create a focused renderer-cache helper under `frontend/scripts/`; add `frontend/scripts/test-mermaid-renderer-cache.mjs` and register the relevant test command without changing lock dependencies.

**Interfaces:** `predev` requests cache reuse explicitly (e.g. `--dev`); default prebuild/pretest behavior always builds. An explicit `--force` rebuilds even with valid dev cache. Keep existing exported `publishRenderer(source, directory)` behavior compatible.

- [x] Add failing behavior tests using disposable directories and an injectable build operation for reuse, changed/added/deleted local inputs, lock/tool/script identity, corrupt/missing output, force/default build and interrupted/concurrent publication.
- [x] Cache fingerprint covers renderer local imports/file set, build script/options, lock and Node/build-tool versions. Do not hash the complete dependency tree. Verify output digest and the existing self-contained classic-script rule on reuse.
- [x] Publish output and metadata atomically, bind recorded digest to that build's generated bytes, recheck input identity before publication, and reject mismatched pairs. Failed/cancelled builds do not publish success.
- [x] Run cache tests and existing renderer-output tests. Run real predev twice and report build/reuse with wall times; verify default build still builds. Root commits only owned files.

### Task 4: Integrate Manager automatic inspection and startup

**Files:** Modify `scripts/manager/operations.py`, `inspection.py`, `ensure.py`; add `scripts/test_manager_developer_startup.py`; extend existing inspection/ensure/one-click tests.

**Interfaces:** Consume Task 1 helper and `validation_policy` request field; pass `validation_policy='developer'` only through dev startup/decision APIs defined by Task 2. Doctor/preparation remain comprehensive. No policy is persisted into production profile metadata.

- [x] Test worker rejection before mutation, developer inspection with inventory/backend-probe functions set to fail if invoked, unchanged managed inspection, and actual policy propagation into startup.
- [x] Test ready ensure under the lease: no inventories/install; fresh backend state still governs schema/admin readiness; lock changes select affected preparation; under-lock changes replan; full doctor remains full even for developer requests.
- [x] Add worker parsing/explicit source binding and skip release-manifest equality only for the explicitly selected editable developer source. Lightweight inspection reads bounded profile/state data without backend/runtime subprocesses or full inventories and labels its limited scope honestly.
- [x] Keep lifecycle resource leases and start/stop semantics. Preparation still invokes full existing checks. Pass optional policy kwargs only where needed to preserve default-call compatibility.
- [x] Run new integration tests and all `scripts/test_manager*.py` and `scripts/test_launcher*.py` groups. Root commits the integrated change.

### Task 5: Acceptance, documentation and final verification

**Files:** Modify `docs/windows-manager.md`, `docs/launcher-runtime.md`, `scripts/manager_windows_acceptance.py`, `scripts/test_manager_windows_acceptance.py`, and `.github/workflows/manager-windows.yml` only as needed to exercise the new native path.

- [x] Extend the existing Windows acceptance to explicitly select developer dev/source context, perform three ready restarts and record policy, phase durations and work counters without exporting private paths or environment content.
- [x] Test the acceptance evidence logic on Linux and keep actual Windows-only cases explicitly gated. Existing packaged managed/prod coverage remains enabled.
- [x] Document opt-in, source-bound selection, full verification, force renderer rebuild, first-time receipts and unchanged production behavior.
- [x] Run `python launcher.py check`, `python launcher.py test`, `python launcher.py prod --help`, all launcher/Manager tests, frontend format/typecheck/build and artifact checks appropriate to the renderer output. Record environment blockers precisely; fix regressions, do not claim unrun Windows timings.
- [x] Run whole-change review for spec compliance and correctness, resolve important findings, update this checklist and summarize delivered behavior and remaining native evidence.


## Implementation and verification record

Completed on 13.11.2026. Developer selection, limited inspection/startup, full verification, dev renderer reuse and native evidence instrumentation are implemented. One real Vite import-resolution cache defect found in final review was reproduced with real builds and fixed; the scoped re-review passed with no remaining Important/Critical findings.

| Check | Result |
| --- | --- |
| Manager discovery | 437 tests OK; 51 platform/display skips |
| Startup metrics | 4 tests OK; real private pipe transport covered in Manager suite |
| New runtime + startup integration groups | 28 tests OK |
| Renderer cache/output | 41 focused tests OK, including real Vite resolution regressions |
| Exact frontend test:ci | 695 tests OK |
| launcher.py check and prod --help | Passed; checks include Django/migration drift-plan and frontend format/typecheck |
| Frontend build / collectstatic / verify_frontend_artifact | Passed; 281 collected files, 21 verified assets |
| Full launcher.py test backend phase | 1462 tests; 4 failures, 1 skip in unchanged isolated-worker descendant-process tests. Same 4 failures reproduced against base 8612d51. Aggregate command stops here; frontend gate was exercised separately. |
| Full launcher discovery with package CA overrides removed | 603 tests; 3 failures, 1 error, 17 skips. Certificate subcases, private-storage fixture and callback fixture failures all reproduced against base 8612d51. |
| Native Windows EXE/Tk/NTFS/ACL/HTTP acceptance and total startup timing | Not run on this Linux executor. CI retains managed/prod coverage and adds three developer restarts with real work counters. |

On the final Linux code, forced renderer preparation took 2.768s, verified warm reuse 0.652s and default full prebuild 2.570s. These are renderer-only preparation measurements, not Windows application startup times. No dependency locks or supported runtime targets changed. Seven obsolete Node test-only flags were removed so the existing .mjs commands execute on supported Node 24.
