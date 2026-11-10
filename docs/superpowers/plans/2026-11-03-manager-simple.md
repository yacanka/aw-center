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

## Reference-fidelity acceptance pass

The user reaffirmed the original Sade yönetim example and allowed Advanced
SystemCare as secondary inspiration. Computer access remained unavailable;
the user explicitly chose to continue with available checks.

- Independent native measurements exposed the half-width settings grid and the
  fixed task panel that clipped primary controls. New tests reproduced both.
- Settings now fill their card, use symmetric 16px field spacing, and share one
  scrolling stack with the task table. Its visible columns match the reference;
  task-ID-bound report and stop behavior remain covered.
- Native measured targets: 30px content alignment, 49px header, 13/25/16px text,
  42px status tile, 16px tab icons, 7/6px control corners. DPI and 150% system
  text scale these roles; an incorrect platform font-size assumption was caught
  and fixed with normal/enlarged-text regression coverage.
- Rounded RGBA control skins and tab icons are generated with standard-library
  code, retained for widget lifetime, and cover light/dark, hover, pressed,
  disabled, readonly and keyboard-focus states. No dependency was added.
- Ready servers stay controller-owned without showing startup progress; a
  dedicated test protects ready-state action visibility at the available size.
- Windows CI now requires a Tk display, rejects startup callback failures,
  and retains non-sensitive startup metadata even on failure.
- Final verification: 157 Manager tests, 153 passed / 4 Windows package skips;
  54 launcher/release tests passed. Source smoke: ready=true, callback errors=0.
  Compile and diff checks passed.
- This is measured layout/control evidence, not a screenshot comparison. The
  available display clamps 1000x820 to 1000x762. Windows EXE rebuild and final
  Windows visual acceptance remain outstanding; no pixel-equality claim is made.

## Responsiveness regression correction

The user reports severe lag and poor visual quality. Keep the approved Sade
layout and existing Tk/controller contracts while correcting measured work.

- [x] Reproduce redundant native redraws with a selected-task event burst and
  verify background events preserve the selected report's selection/scroll.
- [x] Coalesce event rendering, avoid redundant tree selection and control
  reconfiguration, and render reports when visible or explicitly selected.
- [x] Normalize wheel movement to small pixel increments; retain keyboard
  scrolling and access to advanced fields.
- [x] Reduce duplicate footer information within the existing layout, keeping
  selected-task stop accessible from every tab.
- [x] Run native regressions, the complete Manager suite, related launcher
  tests and the source startup smoke; record actual before/after measurements.

Initial evidence: 200 status events caused 402 full refreshes and 201 synthetic
selection callbacks. Removing skins, disabling card drawing, removing card
Canvases, stopping progress, or disabling wrapping individually did not materially
improve the native resize probe. Do not claim those decorations caused the lag.

The idle-lag report led to a confirmed native rendering cause: ttk tiles image
elements rather than scaling them. The new 1x1 transparent tab spacer was tiled
across the whole tab. Nine identical tab interactions took 2.509 CPU seconds,
versus 0.007 for built-in tabs. The new relative-cost regression failed first.
The spacer now uses no fill; tab backgrounds have a large uniform centre.
Rounded control skins likewise use a 63x63 centre instead of 3x3, preserving
corners, focus states and minimum control sizes without thousands of tile calls.

Same-host Tk 9.0.4 probe: construction 2.956 -> 0.279 seconds; initial two-second
idle CPU 0.874 -> 0.046 seconds; 30 resize steps now complete in 1.290 seconds
(the old version hit the 12-second watchdog before all steps completed).
The combined task creation + 200-event burst now renders twice instead of 402
times; status-only regression renders once, and background-event regression
renders zero times while retaining all events. These are macOS native timings,
not Windows EXE performance or screenshot acceptance.

Independent review found no correctness/lifecycle/security blocker. Its scroll
coverage suggestion was addressed with a long, visibly scrolled report fixture.
A pending-refresh owner-switch regression also verifies report/error isolation.
Explicitly expanding an initially empty list is covered by real widget mapping.

Final verification: 165 Manager tests (161 passed, 4 Windows package skips),
54 related launcher/release tests passed, Python compilation and diff checks
passed. Source startup evidence reports ready=true and callback_error_count=0.
Computer-use inventory still reports an unavailable native service and disabled
browser access, so screenshot/visual equality is not claimed. GitHub workflow
lookup returned HTTP 404 because manager-windows.yml is not yet on the default
branch; no workflow was dispatched and no PR was opened. A rebuilt Windows EXE
and visual acceptance remain required.
