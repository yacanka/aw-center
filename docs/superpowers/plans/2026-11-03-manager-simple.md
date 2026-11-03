# Manager Simple UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the user-approved Sade yönetim layout to the existing Manager window.

**Architecture:** Keep Tkinter/ttk and the controller/view-model boundary. Change
presentation and progressive disclosure in `view.py`; retain task and form state.

**Tech Stack:** CPython 3.11, standard-library Tkinter/ttk and unittest.

**Spec:** `docs/superpowers/specs/2026-11-03-manager-simple-design.md`

## Global Constraints

- Preserve the current working tree, including existing Python/.env changes.
- No dependency, lifecycle, packaging or backend/frontend contract changes.
- No automatic commit, branch change, reset, installation or production operation.
- Work in the existing feature checkout so its uncommitted changes are retained.

## Review Focus

- An advanced-field validation error must reveal its widget before focus.
- Form profile edits must not relabel a running task's summary.
- A finishing task remains active until controller cleanup completes.
- Long text and 700×560 windows must retain scroll/keyboard access.
- Moving actions must preserve all callbacks, stop scope and sanitized reports.

### Task 1: Window presentation and regression coverage

**Files:** `scripts/manager/view.py`, `scripts/test_manager_view.py`.

**Interfaces:** Preserve `ManagerWindow`'s controller-facing interface and all
five `action_buttons`. Add `_set_advanced(bool)`, `_toggle_advanced()` and
`_update_summary()` with Tk variables for disclosure and selected-task metadata.

- [x] Add headless disclosure/summary tests and observe failures first.
- [x] Add theme-derived styles, status banner, simplified run form, collapsible
  advanced settings, per-tab actions and task list below the notebook.
- [x] Preserve field-error focus, profile-specific controls, selection and reports.
- [x] Run manager tests; run native Tk tests outside the macOS sandbox when needed.

### Task 2: Documentation and final review

**Files:** `docs/windows-manager.md` and this plan.

- [x] Document the new layout and location of advanced options.
- [x] Run Manager and relevant launcher suites, syntax and diff checks.
- [x] Obtain independent review; address concrete regressions and recheck.
- [x] Report actual verification and Windows-only remaining checks.

## Verification record

- Before implementation: 119 Manager tests, 14 skipped in the sandbox.
- New disclosure/summary tests first failed as expected, then passed.
- Independent review identified small-window space, wrapping and keyboard-focus
  regressions. Native regression tests reproduced them before the fixes.
- Small windows / large fonts now collapse task details without losing selection.
  Error cards show a measured short summary with complete recovery text in reports.
- A full native run exposed wrap/requested-width feedback during error reveal.
  Fixed by giving wrapped labels a minimal requested width while grid supplies
  their displayed width; all native tests then completed together.
- Final Manager suite: 134 tests, 130 passed, 4 Windows package tests skipped.
- Related launcher/release/Python/environment suites: 79 tests passed.
- Native 700×560 / 150% font / long-error access tests passed; five installed ttk
  themes opened successfully. Source entrypoint smoke returned `ready: true`.
- Python compilation and `git diff --check` passed.
- Windows EXE build and Windows visual acceptance require native Windows.
  Screenshot inspection was unavailable because computer-use services were disabled.
