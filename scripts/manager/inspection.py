"""Read-only profile inspection; opening Manager never provisions a profile."""
from pathlib import Path

from scripts.launcher.installation import require_windows, _core_checks, _runtime_options
from scripts.launcher.installation_profiles import installation_home, load_profile
from scripts.launcher.installation_permissions import require_unlinked
from scripts.launcher.toolchain import inspect_toolchain


def inspect_profile(args, emit):
    require_windows()
    home = installation_home()
    if getattr(args, 'source_selection', None) == 'automatic':
        from .ensure import resolve_source
        resolve_source(args, home)
    path = home / 'config' / (args.profile + '.profile.json')
    require_unlinked(path)
    if not path.exists():
        pending = path.with_name(args.profile + '.pending.json')
        env = path.with_name(args.profile + '.env')
        # Pending metadata is recovered only by explicit provision. An orphan
        # environment cannot safely be treated as a fresh install.
        require_unlinked(pending)
        require_unlinked(env)
        status = 'incomplete' if pending.is_file() else 'blocked' if env.exists() else 'not_installed'
        from scripts.launcher.runtime_selection import tool_choices
        tools = tool_choices(args)
        summary = ' · '.join(f"{label} — {'sistem kurulumu' if field in tools else 'seçilen kaynaklardan hazırlanacak'}"
                            for label, field in (('Python 3.11', 'python_executable'), ('Node.js', 'node_executable')))
        emit({'type': 'profile', 'profile': args.profile, 'status': status,
              'tools': summary,
              'detail': 'İlk kurulum gerekli.' if status == 'not_installed' else 'Özel profil hazırlığı tamamlanmalı.'})
        return
    from .operations import _project_for
    project = _project_for('doctor', args)
    profile = load_profile(project, args.profile, home)
    runtime = inspect_toolchain(home, **_runtime_options(profile))
    backend = {}
    checks = list(runtime)
    if all(row['status'] == 'ready' for row in runtime):
        checks.extend(_core_checks(project, profile, observed_backend=backend, managed_build=True))
    status = 'stopped'
    if any(row['status'] not in {'ready', 'available'} for row in checks):
        status = 'incomplete'
    if backend:
        schema = backend['schema']
        if schema in {'pending', 'error', 'missing'}:
            from scripts.launcher.installation_profiles import read_profile_environment
            database = Path(read_profile_environment(profile)['DATABASE_URL'].removeprefix('sqlite:///'))
            status = 'incomplete' if schema == 'pending' or not database.exists() else 'blocked'
    if any(row['status'] == 'invalid' for row in checks):
        status = 'blocked'
    tools = ' · '.join(f"{label}: {'sistem kurulumu' if profile.get(field) else 'yönetilen kurulum'}"
                      for label, field in (('Python 3.11', 'python_executable'), ('Node.js', 'node_executable')))
    emit({'type': 'profile', 'profile': args.profile, 'status': status, 'checks': checks,
          'tools': tools, 'detail': 'Ortam başlatılmaya hazır.' if status == 'stopped' else
          'Eksikleri inceleyin; mevcut veriler ve anahtarlar korunur.'})
