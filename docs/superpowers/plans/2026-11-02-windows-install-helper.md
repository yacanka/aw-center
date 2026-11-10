# Windows installation helper implementation plan

Goal: a double-click CMD wizard that prepares and runs AW Center on Windows x64,
starting with development and preserving the existing Windows production lifecycle.

## Binding decisions

- No PowerShell. Bootstrap uses Windows curl.exe, certutil.exe, tar.exe and CMD;
  application workflows remain Python standard-library modules under scripts/launcher.
- Sources: public HTTPS, selected package repository, then offline directory. Verify
  versions and checksums, preserve lock files, never disable TLS verification.
- Managed runtimes and private config live outside the checkout under LOCALAPPDATA.
  Python 3.11, Node 22 and the repository npm pin remain canonical.
- Explicit provisioning creates keys once. Existing keys, accounts and business
  state are never reset. Doctor is read-only. Normal start never migrates.
- Attempt every supported feature; distinguish core readiness from missing licensed
  software, private assets and external configuration. Core may run with gaps.
- Foreground lifecycle only, reusing Job Object/process-tree containment.
- Prod consumes supplied IPv4/TLS/firewall configuration and keeps existing gates.
  No OS security changes, service installation, database reset or automatic upgrade.
- Initial delivery is the helper inside an extracted source package/checkout;
  cloning or authenticating to a Git repository is not a prerequisite.

## Tasks and module ownership

1. CMD bootstrap, trusted tool catalog, artifact retrieval and managed toolchain.
2. Owner-restricted profiles, provisioning, read-only profile/backend inspection.
3. Full offline bundle, optional feature inventory and approved asset installation.
4. CLI/wizard orchestration and readiness through existing runtime supervision.
5. Documentation, Windows CMD smoke CI, regression tests and independent review.

## Interfaces agreed before implementation

- installation_sources.py: Artifact dataclass (name, version, filename, url,
  sha256, archive, executable); SourceSettings dataclass (repository, offline_dir,
  python_index_url, npm_registry_url, ca_file); fetch_artifact(artifact, cache,
  settings) -> Path; load_catalog() -> dict[str, Artifact].
- toolchain.py: ensure_toolchain(home, settings) -> dict[str, str] returning
  process-local PATH overrides; inspect_toolchain(home) -> list[dict] with
  name/status/detail; no global PATH or dependency-lock mutation.
- installation_profiles.py: installation_home() -> Path;
  load_profile(project, name, home=None) -> dict;
  provision_profile(project, name, home=None, **options) -> dict;
  profile_environment(profile) -> dict[str, str];
  inspect_profile(project, profile) -> list[dict]. Profiles carry name, source_root,
  env_file, host, backend_port, frontend_port, tls_cert_file, tls_key_file,
  asset_set, exclude_doors. Existing profiles never overwrite source_root.
- installation_features.py: inspect_features(project, profile) -> list[dict];
  install_features(project, profile, settings) -> list[dict]. Only reviewed
  catalog artifacts may execute; missing business inputs are reported.
- installation_bundle.py: prepare_install_bundle(project, output, settings,
  assets=None) -> Path; verify_install_bundle(project, directory) -> dict.
  Dependency manifests stay in a dedicated dependencies/ subdirectory and keep
  their existing format. Include source and bootstrap files without secrets.
- Root owns installation.py, installation_cli.py, installation_readiness.py,
  parser.py/cli.py/runtime.py/job_worker.py adaptations, docs and CI integration.
- Public commands: wizard, provision --profile dev|prod, doctor --profile dev|prod,
  start --profile dev|prod, prepare-install-bundle --output PATH.

## Verification

Use focused unittest suites plus existing launcher/release regressions. Add Windows
CMD smoke for bootstrap with no inherited Python/Node/Git PATH, fallback, ACL,
idempotency, readiness and cleanup. Verify backend env/production/SQLite tests and
frontend build/static/artifact gates. Hosted tests cannot prove real DOORS/Office
licenses or corporate connectivity; require an explicit Windows acceptance run.
