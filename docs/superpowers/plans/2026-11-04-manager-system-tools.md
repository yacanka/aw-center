# Manager System Tools Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Reuse compatible system Python/Node, acquire only missing managed tools, and expose Node selection in Manager.

**Architecture:** Add Node discovery alongside system_python. Thread explicit tool pointers through existing toolchain and profile lifecycle; version offline manifests only when external host tools replace archives.

**Tech Stack:** Standard-library Python, Tk, Windows subprocesses; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-04-manager-system-tools-design.md`

## Global Constraints

- CPython 3.11 x64 with venv/ensurepip; Node x64 22.12+ within major 22 or Node 24+.
- npm remains 10.9.4; included runtime archives remain catalog/hash verified.
- No shell command parsing, private path output, credential persistence, or cancellation fallback.
- Preserve version 1 bundles and CLI defaults; external tool bundles use version 2.

## Review Focus

- Paths with spaces/quotes resolve consistently in picker, preferences and worker.
- Installed incompatible tools cause automatic fallback, explicit incompatible tools fail.
- A valid system Node must not trigger a Node archive request, including bundling.
- A saved system Node is validated on restart rather than replaced with managed Node.
- Missing prerequisites in version 2 offline bundles remain actionable and fail closed.

### Task 1: Node discovery and toolchain

**Files:** Create `scripts/launcher/system_node.py`, `scripts/test_launcher_system_node.py`; modify `scripts/launcher/toolchain.py`.

**Interfaces:** `discover_node(selection: str | None = None) -> Path`, `validate_node(executable: Path) -> Path`, `find_npm_cli(node: Path, version: str) -> Path | None`, `SystemNodeError` with safe code/remedy. Existing toolchain functions gain optional `node_executable: Path | None = None`.

- [x] Add failing discovery, architecture/version, explicit-path and cancellation tests.
- [x] Implement bounded probes with isolated Node environment and no shell.
- [x] Add failing toolchain tests proving selected system Node is never fetched, matching npm reused, missing npm alone acquired.
- [x] Implement optional Node selection across ensure/inspect/environment and run focused tests.

### Task 2: Bundle host prerequisites

**Files:** `scripts/launcher/installation_bundle.py`, `scripts/test_launcher_bundle.py`.

**Interfaces:** `prepare_install_bundle(..., external_runtimes=frozenset())`; only `python`, `node`, `npm` allowed. Version 2 `host_runtimes` maps omitted names to producer version strings; no paths.

- [x] Add failing tests for omitted archives/no fetch, exact host metadata and tamper rejection.
- [x] Implement version 2 preparation/validation; preserve strict complete version 1 validation.
- [x] Validate actual dependency toolchain versions against host metadata and supported Node constraints.
- [x] Run bundle tests including unchanged v1 and trust-boundary cases.

### Task 3: Manager form and preferences

**Files:** `scripts/manager/view.py`, `view_model.py`, `paths.py`; related Manager view/preferences tests.

- [x] Add failing Node command/path picker, relative/quoted path normalization and preference round-trip tests.
- [x] Add remembered `node_command` field; permit file/directory/executable-name selections, never shell expressions.
- [x] Update Python checkbox/help to explain auto-first and managed fallback; run relevant UI/headless tests.

### Task 4: Lifecycle integration

**Files:** `scripts/manager/operations.py`, `scripts/launcher/installation.py`, `installation_profiles.py`; lifecycle/profile/Manager tests; `docs/windows-manager.md`.

- [x] Add failing automatic-Python fallback, Node selection, restart, and no-download Manager bundle tests.
- [x] Resolve choices once per operation; preserve explicit errors and cancellation; persist validated Node pointer independently of env/keys.
- [x] Pass Node through provision/start/doctor and pass external names to Manager bundle creation.
- [x] Document changed selection and target prerequisites, run all script tests and launcher check.
- [x] Obtain independent review and fix findings.

Integration: commit and push the verified changes under standing user authorization.

## Verification record

523 script tests completed: 466 passed, 57 skipped. Launcher check, frontend build, collectstatic and frontend artifact verification passed. A prior run hit the existing macOS process-group cleanup permission race in a transport test; its focused rerun and the final full suite passed. Native Windows verification follows push.
