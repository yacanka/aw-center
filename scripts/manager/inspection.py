"""Read-only profile inspection; opening Manager never provisions a profile."""
from pathlib import Path

from scripts.launcher.installation import require_windows
from scripts.launcher.installation_profiles import installation_home, load_profile
from scripts.launcher.installation_permissions import require_unlinked, require_private
from scripts.launcher.model import Project


def _metadata_inspection(args, home, path, emit):
    """Bounded metadata observation; startup performs its own fresh checks."""
    from scripts.launcher.model import LauncherError
    # load_profile also checks the other profile's state separation. Bound every
    # file it may read before entering that shared, strict validation routine.
    for name in ('dev', 'prod'):
        for suffix in ('.profile.json', '.env', '.pending.json'):
            candidate = home / 'config' / (name + suffix)
            require_unlinked(candidate)
            if candidate.exists() and (not candidate.is_file() or candidate.stat().st_size > 64 * 1024):
                raise LauncherError('Profil metadata boyutu veya dosya türü doğrulanamadı.')
    pending = path.with_name(args.profile + '.pending.json')
    if not path.exists():
        env = path.with_name(args.profile + '.env')
        status = 'incomplete' if pending.exists() else 'blocked' if env.exists() else 'not_installed'
        tools = ''
    else:
        from .operations import _project_from_layout
        profile = load_profile(_project_from_layout(Path(args.source_root)), args.profile, home)
        status = 'incomplete' if pending.exists() else 'stopped'
        tools = ' · '.join(f"{label}: {'sistem kurulumu' if profile.get(field) else 'yönetilen kurulum'}"
                          for label, field in (('Python 3.11', 'python_executable'), ('Node.js', 'node_executable')))
    emit({'type': 'profile', 'profile': args.profile, 'status': status, 'tools': tools,
          'source_root': str(args.source_root),
          'validation_policy': 'developer', 'checks': [],
          'detail': 'Hızlı kontrol. Yalnız profil kayıtları okundu; bağımlılıklar ve şema açılışta denetlenir.'})


def inspect_profile(args, emit):
    """Read profile metadata for the window; explicit diagnostics use doctor."""
    from scripts.launcher.validation_policy import require_validation_policy
    from .paths import default_source_root
    policy = require_validation_policy(getattr(args, 'validation_policy', 'managed'),
                                       profile=args.profile, source_selection=args.source_selection)
    require_windows()
    args.source_root = getattr(args, 'source_root', None) or str(default_source_root())
    home = installation_home()
    path = home / 'config' / (args.profile + '.profile.json')
    if getattr(args, 'source_selection', None) == 'automatic':
        from .ensure import resolve_source
        resolve_source(args, home)
    if policy == 'developer':
        return _metadata_inspection(args, home, path, emit)
    require_unlinked(path)
    if not path.exists():
        pending = path.with_name(args.profile + '.pending.json')
        env = path.with_name(args.profile + '.env')
        # Pending metadata is recovered only by explicit provision. An orphan
        # environment cannot safely be treated as a fresh install.
        require_unlinked(pending)
        require_unlinked(env)
        status = 'incomplete' if pending.is_file() else 'blocked' if env.exists() else 'not_installed'
        emit({'type': 'profile', 'profile': args.profile, 'status': status,
              'source_root': str(args.source_root),
              'tools': 'Python 3.11 ve Node.js kurulum sırasında denetlenecek.',
              'detail': 'İlk kurulum gerekli.' if status == 'not_installed' else 'Özel profil hazırlığı tamamlanmalı.'})
        return
    _profile_summary(args, home, emit)


def _profile_summary(args, home, emit):
    """Keep automatic inspection independent of source and installed-code scans."""
    source = Path(args.source_root).absolute()
    require_unlinked(source)
    # Manager packages use the repository's fixed layout. Discovery would walk
    # the source tree; actual startup still selects and validates the release.
    project = Project(source.resolve(), source / 'backend/manage.py',
                      source / 'frontend/package.json', source / 'requirements.txt')
    profile = load_profile(project, args.profile, home)
    pending = home / 'config' / (args.profile + '.pending.json')
    require_unlinked(pending)
    if pending.exists():
        require_private(pending)
    required = (project.manage_py, project.package_json, project.python)
    for path in required:
        require_unlinked(path)
    incomplete = pending.exists() or any(not path.is_file() for path in required)
    tools = ' · '.join(f"{label}: {'sistem kurulumu' if profile.get(field) else 'yönetilen kurulum'}"
                      for label, field in (('Python 3.11', 'python_executable'), ('Node.js', 'node_executable')))
    emit({'type': 'profile', 'profile': args.profile,
          'source_root': str(args.source_root),
          'status': 'incomplete' if incomplete else 'unverified', 'tools': tools,
          'detail': ('Kayıtlı hazırlık tamamlanmalı; AW Center’ı aç ile eksikler denetlenecek.' if incomplete else
                     'Profil kayıtlı. Başlatma gereksinimleri uygulama açılırken doğrulanacak; '
                     'ayrıntılı denetim için Durumu denetle kullanın.')})
