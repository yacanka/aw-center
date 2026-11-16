# Manager opening and environment usability

**Goal:** Restore the existing one-click design by removing work before it is
needed, reusing verification within a single locked start, and accepting normal
literal environment-file syntax with actionable errors.

**Spec:** `docs/superpowers/specs/2026-11-09-aw-center-manager-tek-tik-promptu.md`

**Scope:** Keep the existing Manager, launcher, profile ownership, separate state,
CPython 3.11, production deployment gates and worker readiness. No dependencies,
database changes, commits or changes to existing compliance edits.

## Tasks

- [x] Make automatic window inspection a metadata summary, without source,
  runtime or dependency inventories, tool discovery or Django subprocesses.
  Retain full explicit diagnostics. Show registered, unverified profiles with
  the same main opening action, without declaring them ready.
- [x] Reuse ready runtime verification only within the same locked startup;
  never persist the result or reuse it after provisioning or lease release.
- [x] For the user's local-only usage, compare dependency receipts and locks
  and inspect the actual backend during dev opening; retain full package byte
  inventories for provisioning, explicit diagnostics and production opening.
- [x] Accept literal export assignments, quoted values and inline comments;
  retain no interpolation/execution, duplicate/control rejection and generated
  profile serialization compatibility. Empty identity settings retain generated
  or registered keys. Existing manual databases still require original keys.
- [x] Identify environment conflicts by safe key names and parsing errors by
  line number. Display the remedy and focus the environment-file field. Update
  help to refer to the main opening action.
- [x] Run the focused tests, the complete scripts suite and an independent
  review. Report native Windows acceptance and timings as unverified here.

## Verification cases

- Window opening performs no executable discovery, inventory hashing or Django
  subprocess, and does not mutate state.
- Full diagnostics and actual starts still reject genuinely corrupted state.
- A snapshot cannot cross lease boundaries, runtime selections or installations.
- Blank example keys cannot rotate keys or bypass manual database adoption.
- Error events expose safe setting names and a remedy, never values or paths.

## Environment evidence

The initial focused run hit sandbox EPERM on every loopback bind, including port
zero. This is a test-environment restriction; it is not evidence of a Manager
port-selection defect. Run socket tests with the existing approved local test
permission. Native Windows/NTFS/TLS end-to-end acceptance remains platform-specific.

Verification: complete scripts suite passed 1,052 tests (27 platform skips).
Independent review's single-quoted trailing-backslash issue was reproduced and
fixed with a regression test. A native small-window layout failure from the
new remedy display was fixed and its focused native tests passed. Console code
received a separate independent review with no Critical/Important findings;
native terminal visibility and window-close acceptance remain unverified.

Follow-up user design: explicit Manager inputs must override ordinary .env
values, with .env values supplying all unset fields. Source stays immutable;
overrides are global; local SQLite backup/migrations and dependency preparation
are automatic; closing the server terminal stops its owned processes while the
GUI stays open. See ../specs/2026-11-13-manager-local-env-design.md. That precedence
redesign is not implemented by this bounded startup patch.
