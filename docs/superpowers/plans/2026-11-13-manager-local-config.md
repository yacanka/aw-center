# Local Manager configuration implementation plan

**Goal:** Apply the approved local SQLite Manager design with explicit Manager
inputs overriding ordinary `.env` values and defaults, without changing source
configuration or existing data.

**Spec:** `docs/superpowers/specs/2026-11-13-manager-local-env-design.md`

**Architecture:** One local configuration resolver produces effective profile
metadata and runtime values. Global raw form inputs remain separate from that
output. Existing private profiles, atomic pending journals, SQLite backups and
owned-process lifecycle are reused. Legacy CLI and production remain strict.

**Constraints:** CPython 3.11.x; no dependencies, real secrets in source/logs,
database reset, migration rewrite, commits or changes to existing compliance edits.

### Task 1: Global explicit form inputs

Files: `scripts/manager/{paths,view_model,view}.py`,
`scripts/test_manager_global_inputs.py`.

- [x] Reproduce context-history overrides restoring an old host/port or erasing
  a cleared value; fix by keeping raw connection overrides global.
- [x] Accept meaningful IPv4/localhost dev binding values without changing prod
  validation. Empty fields remain empty and retain fallback semantics.
- [x] Update the existing help text and run preferences/adaptive/view tests.

### Task 2: Local resolution and durable profile publishing

Files: new `scripts/launcher/installation_local_config.py`, existing
`installation_profiles.py`, `installation_env.py`, `installation_connection.py`,
`installation.py` provisioning integration, `scripts/manager/ensure.py`.

Interfaces: `resolve_local_configuration(project, args, profile=None)` returns
candidate profile and runtime mapping without writes;
`apply_local_configuration(project, args, profile=None)` publishes and returns
the profile; `configuration_changed(project, args, profile)` compares inputs.

- [x] Write failing tests for precedence, field clearing, changed/deleted env
  keys, backend-relative SQLite/media/model paths and immutable source bytes.
- [x] Resolve fresh defaults + selected env + current explicit Manager inputs.
  Env ports are manual; defaults or explicit auto may find a free port.
- [x] Preserve supplied keys; missing keys may reuse only an identity-bound
  private key record. Refuse key generation for an unknown populated database.
  Test new database A → B → A and existing database adoption.
- [x] Validate marked dev configuration semantically, retaining path/secret/
  production separation checks. Preserve direct CLI and production contracts.
- [x] Journal arbitrary profile/environment changes with immutable private
  candidate content, recovering before/after each publication boundary without
  rereading a changed source env. Test crash recovery and no partial data writes.
- [x] Use the same resolution for one-click decisions and preparation; preserve
  source-selected asset paths during optional asset setup.

### Task 3: End-to-end launch integration

Files: `scripts/manager/operations.py`, `installation_readiness.py`,
`scripts/manager/payload.py`, new `scripts/test_manager_local_config_flow.py`.

- [x] Test explicit start/doctor comparisons using saved override provenance,
  not a second strict legacy import or yesterday's resolved values.
- [x] Use the existing `runtime.public_url` for wildcard-host readiness/browser
  URLs, retaining actual bind values for server processes.
- [x] Include the new resolver in Manager source distribution.
- [x] Exercise the main action across file changes, cleared overrides, existing
  database switches, safe migration and restart. Native Windows checks remain
  explicit where unavailable.

### Task 4: Review and verification

- [x] Run focused local resolver, profile, env, connection, Manager and backup
  suites; inspect every failure rather than weakening assertions.
- [x] Run complete scripts discovery, compile checks and `git diff --check`.
- [x] Obtain an independent review against the approved spec and address
  material findings. Update the Manager guide with the final behavior.

## Review focus

Source changes while running; Manager override removed rather than merely empty
in output; a deleted env key disappearing; same database with source-supplied
new keys versus a different database; interrupted profile/environment/key
publication; env-specified occupied ports; wildcard bind with loopback browser.

## Progress

Task 1: 140 focused tests passed (27 native/platform skips). Broad Manager test
found the existing fixture's fake provision path preserving stale default-origin
metadata; integration will reproduce and resolve it without dropping coverage.
Tasks 2–4 complete in the current working tree. No commits or application data
changes were made; pre-existing compliance edits remain untouched.

## Revalidation after upstream sync — 14.11.2026

Reference: main and origin/main both at `5a3bbac`. The draft remained uncommitted
while the upstream source-bound developer-mode feature was merged.

- Removed the draft's implicit fast dev branch; the upstream explicit
  `managed`/`developer` policy is the single authority. Required Vite/Python
  outputs are checked; managed package integrity remains comprehensive.
- Retained automatic generated-package replacement only for explicit developer
  Manager preparation. The managed path retains its strict integrity boundary.
- Preserved legacy database keys before first database switch, including pending
  recovery; kept cumulative validated output history for packaged restarts.
- Manifest-owned source files remain verified. Local SQLite/private/cache/asset
  output history may exclude only non-source paths; source manifest is unchanged.
- Fixed mixed-snapshot packaged recovery admission and replay ordering when the
  selected source is missing/invalid. Generated config/key/profile/journal source
  self-references remain rejected before mutation.
- Normalized dev/prod storage identity and writable-directory overlap checks,
  retaining shared read-only assets.
- Corrected macOS temporary test paths without weakening symlink protection.

Final evidence: complete scripts discovery ran 1,183 tests: 1,156 passed,
27 skipped, no failures/errors. Compile checks, launcher prod --help and
`git diff --check` passed. Independent scoped re-review approved the fixes.
Native Windows console visibility/close semantics and NTFS acceptance were not
run on this macOS host; no Windows timing improvement is claimed.
