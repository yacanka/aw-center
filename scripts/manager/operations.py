"""Action execution inside one isolated OS worker per desktop operation.

Launcher environment contexts are process-wide: never run these handlers in
threads sharing an interpreter. Imports for an action stay in its own path.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from scripts.launcher.model import LauncherError
from scripts.launcher.process import OperationCancelled, check_cancelled, operation_control
from .task_policy import ACTION_LABELS

PATH_FIELDS = {'offline_dir', 'ca_file', 'assets', 'feature_catalog', 'tls_cert_file', 'tls_key_file', 'output'}
TEXT_FIELDS = {'repository', 'python_index_url', 'npm_registry_url', 'host', 'asset_set'}


def arguments(request):
    """Convert only declared form values; paths remain argv elements, never shell."""
    profile = request.get('profile', 'dev')
    mode = request.get('source_mode', 'online')
    if profile not in {'dev', 'prod'} or mode not in {'online', 'corporate', 'offline'}:
        raise LauncherError('Geçersiz profil veya kaynak modu.')
    action = request.get('action', 'provision')
    sources = {'repository', 'offline_dir', 'python_index_url', 'npm_registry_url', 'ca_file'}
    fields = (sources if action == 'test-sources' else
              sources | {'assets', 'feature_catalog', 'output'} if action == 'bundle' else
              PATH_FIELDS | TEXT_FIELDS if action == 'provision' else set())
    values = {'profile': profile, 'source_mode': mode, 'no_admin': False, 'use_saved_sources': False,
              'migrate': request.get('migrate') is True, 'exclude_doors': None}
    for field in PATH_FIELDS | TEXT_FIELDS:
        value = request.get(field) if field in fields else None
        if value is not None and (not isinstance(value, str) or len(value) > 8192 or any(c in value for c in '\0\r\n')):
            raise LauncherError('Geçersiz alan değeri.')
        values[field] = Path(value) if value and field in PATH_FIELDS else value or None
    for field in ('backend_port', 'frontend_port'):
        raw = request.get(field) if action == 'provision' else None
        value = int(raw) if raw not in ('', None) else None
        if value is not None and not 1 <= value <= 65535:
            raise LauncherError('Geçersiz port.')
        values[field] = value
    return argparse.Namespace(**values)


def _bundled_tools(args, emit):
    """Runtime archives ship beside EXE; package indexes need not host CPython."""
    from scripts.launcher.installation import source_settings
    from scripts.launcher.installation_sources import SourceSettings
    from scripts.launcher.installation_profiles import installation_home
    from scripts.launcher.installation_state import installation_lock
    from scripts.launcher.toolchain import ensure_toolchain
    if getattr(sys, 'frozen', False):
        emit({'type': 'phase', 'message': 'Paket içindeki Python, Node ve npm doğrulanıyor'})
        with installation_lock(installation_home()):
            ensure_toolchain(installation_home(), SourceSettings(
                offline_dir=Path(sys.executable).parent, mode='offline'))
    else:
        # Source development still uses the selected policy; no global install.
        with installation_lock(installation_home()):
            ensure_toolchain(installation_home(), source_settings(args))


def _remedy(phase):
    if 'yönetici' in phase:
        return 'İlk yönetici bilgilerini ve parola kurallarını kontrol edip yeniden deneyin. Mevcut hesaplar değiştirilmez.'
    if 'şema' in phase or 'Production' in phase:
        return 'Profil, veritabanı yedeği ve production için IPv4/TLS dosyalarını kontrol edin. Bekleyen migration için açık onay kutusunu kullanın.'
    if 'bağımlılık' in phase or 'runtime' in phase:
        return 'Kaynakları test edin. Python paketi, npm deposu ve runtime arşivleri ayrı kaynaklardır. ZIP paketinin tamamını çıkardığınızdan emin olun.'
    return 'Kaynakları ve profil ayarlarını kontrol edin. Kontrol et ile eksikleri görüntüleyip yeniden deneyin.'


def _failure_reason(error):
    """Translate reviewed error categories, never interpolate exception payloads."""
    if not isinstance(error, LauncherError):
        return 'operation_failed', 'İşlem tamamlanamadı; yapılandırma veya sistem erişimi doğrulanamadı.'
    text = str(error).casefold()
    categories = (
        (('yalnız windows',), 'windows_required', 'Bu kurulum işlemi Windows x64 gerektirir.'),
        (('sha-256', 'checksum', 'hash', 'integrity', 'differ', 'değişmiş'), 'integrity_failed', 'Dosya bütünlüğü doğrulanamadı; değiştirilmiş paket kullanılmadı.'),
        (('tls', 'certificate', 'certification', 'ssl'), 'tls_failed', 'TLS sertifikası veya güvenli bağlantı doğrulanamadı.'),
        (('python artifact unavailable',), 'python_runtime_missing', 'Doğrulanmış Python runtime arşivi bulunamadı.'),
        (('node artifact unavailable', 'npm artifact unavailable'), 'runtime_missing', 'Doğrulanmış Node/npm runtime arşivi bulunamadı.'),
        (('kilitli python', 'python paket'), 'python_packages_missing', 'Kilitli Python paketleri seçilen kaynaklardan edinilemedi.'),
        (('npm', 'frontend paket'), 'npm_packages_missing', 'Kilitli frontend paketleri seçilen kaynaklardan edinilemedi.'),
        (('acl', 'owner', 'different user', 'başka bir'), 'storage_unavailable', 'Özel kurulum alanının sahibi, izinleri veya işlem kilidi doğrulanamadı.'),
        (('migration', 'şema'), 'schema_unavailable', 'Veritabanı şeması hazır değil; migration ve yedek durumunu kontrol edin.'),
        (('yönetici', 'administrator'), 'administrator_failed', 'İlk yönetici oluşturulamadı; kullanıcı adı ve parola kurallarını kontrol edin.'),
        (('profile', 'profil', 'localappdata'), 'profile_unavailable', 'Profil veya ayrı dev/prod yapılandırması doğrulanamadı.'),
        (('süre sınırı', 'timeout'), 'operation_timeout', 'İşlem süre sınırında tamamlanamadı.'),
        (('source', 'kaynak', 'manifest'), 'source_unavailable', 'Kaynak paketi, envanter veya depo ayarları doğrulanamadı.'),
    )
    for patterns, code, reason in categories:
        if any(pattern in text for pattern in patterns):
            return code, reason
    return 'operation_failed', 'İşlem tamamlanamadı; Kontrol et raporundaki eksikleri inceleyin.'

def execute(request, emit, admin_provider, stop):
    """Map only declared results/errors; a failure belongs to this worker alone."""
    phase = 'Hazırlık'
    try:
        if not isinstance(request, dict) or request.get('action') not in ACTION_LABELS:
            raise LauncherError('Geçersiz işlem.')
        args = arguments(request)
        from .paths import default_source_root
        args.source_root = request.get('source_root') or str(default_source_root())
        args.admin_provider = admin_provider
        def progress(label):
            nonlocal phase
            check_cancelled()
            phase = label
            emit({'type': 'phase', 'message': label})
        args.progress = progress
        with operation_control(stop):
            check_cancelled()
            _dispatch(request['action'], args, emit)
        emit({'type': 'done', 'ok': True})
    except OperationCancelled:
        emit({'type': 'status', 'message': 'İşlem durduruldu. Tamamlanan adımlar korunuyor.'})
        emit({'type': 'done', 'ok': True, 'cancelled': True})
    except Exception as error:
        code, reason = _failure_reason(error)
        emit({'type': 'error', 'code': code, 'message': f'{phase}: {reason}', 'remedy': _remedy(phase)})
        emit({'type': 'done', 'ok': False})


def _project_for(action, args):
    from scripts.launcher.discovery import discover_project
    from scripts.launcher.installation import require_windows
    from scripts.launcher.installation_profiles import installation_home
    require_windows()
    source = Path(args.source_root)
    if args.profile == 'prod' and action != 'bundle':
        from .payload import resolve_production_source, stage_production_source
        args.progress('Production kaynakları doğrulanıyor')
        select = stage_production_source if action == 'provision' else resolve_production_source
        source = select(source, installation_home())
    elif getattr(sys, 'frozen', False) and not (source / '.git').exists():
        from .payload import verify_source_payload
        verify_source_payload(source)
    return discover_project(source)


def _dispatch(action, args, emit):
    if action == 'test-sources':
        from .source_checks import run
        run(args, emit)
        return
    project = _project_for(action, args)
    if action == 'doctor':
        from scripts.launcher.installation import doctor
        emit({'type': 'checks', 'checks': doctor(project, args.profile)})
    elif action == 'bundle':
        _bundle(project, args, emit)
    else:
        _lifecycle(project, action, args, emit)


def _bundle(project, args, emit):
    from scripts.launcher.installation import source_settings
    from scripts.launcher.installation_bundle import prepare_install_bundle
    from scripts.launcher.installation_profiles import installation_home
    from scripts.launcher.installation_state import process_environment
    from scripts.launcher.toolchain import inspect_toolchain, toolchain_environment
    if not args.output:
        raise LauncherError('Offline paket hedefi gerekli.')
    # A running app already has verified tools. Bundling then uses them read-only
    # and touches only isolated staging/cache/output, never the live .venv.
    if any(check['status'] != 'ready' for check in inspect_toolchain(installation_home())):
        args.progress('Yönetilen runtime hazırlığı')
        _bundled_tools(args, emit)
    args.progress('Offline paket hazırlanıyor')
    with process_environment(toolchain_environment(installation_home())):
        prepare_install_bundle(project, args.output, source_settings(args, project),
                               assets=args.assets, feature_catalog=args.feature_catalog)


def _lifecycle(project, action, args, emit):
    from scripts.launcher.installation import provision, start_profile
    if action == 'provision':
        args.progress('Yönetilen runtime hazırlığı')
        _bundled_tools(args, emit)
        emit({'type': 'checks', 'checks': provision(project, args)})
    args.progress('Uygulama ve worker süreçleri başlatılıyor')
    def ready(profile):
        check_cancelled()
        url = (f"https://{profile['host']}:{profile['backend_port']}/app/" if profile['name'] == 'prod' else
               f"http://{profile['host']}:{profile['frontend_port']}/app/")
        emit({'type': 'ready', 'url': url})
    start_profile(project, args.profile, on_ready=ready)
