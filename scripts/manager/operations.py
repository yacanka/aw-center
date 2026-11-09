"""Action execution inside one isolated OS worker per desktop operation.

Launcher environment contexts are process-wide: never run these handlers in
threads sharing an interpreter. Imports for an action stay in its own path.
"""
from __future__ import annotations

import argparse
import errno
import os
from pathlib import Path
import sys

from scripts.launcher.model import LauncherError
from scripts.launcher.process import OperationCancelled, check_cancelled, operation_control
from .task_policy import ACTION_LABELS

PATH_FIELDS = {'offline_dir', 'ca_file', 'assets', 'feature_catalog', 'tls_cert_file', 'tls_key_file', 'output', 'env_file', 'manager_distribution'}
TEXT_FIELDS = {'repository', 'python_index_url', 'npm_registry_url', 'host', 'asset_set', 'python_command', 'node_command'}


def arguments(request):
    """Convert only declared form values; paths remain argv elements, never shell."""
    profile = request.get('profile', 'dev')
    mode = request.get('source_mode', 'restricted')
    if profile not in {'dev', 'prod'} or mode not in {'online', 'restricted', 'corporate', 'offline'}:
        raise LauncherError('Geçersiz profil veya kaynak modu.')
    action = request.get('action', 'provision')
    sources = {'repository', 'offline_dir', 'python_index_url', 'npm_registry_url', 'ca_file'}
    fields = (sources if action == 'test-sources' else
              sources | {'assets', 'feature_catalog', 'output', 'python_command', 'node_command', 'manager_distribution'} if action == 'bundle' else
              PATH_FIELDS | TEXT_FIELDS if action in {'provision', 'ensure'} else {'python_command', 'node_command'} if action == 'inspect' else {'env_file'} if action in {'start', 'doctor'} else set())
    values = {'profile': profile, 'source_mode': mode, 'no_admin': False, 'use_saved_sources': False,
              'migrate': request.get('migrate') is True, 'exclude_doors': None,
              'install_python': request.get('install_python') is True}
    values['install_node'] = request.get('install_node') is True
    values['source_selection'] = request.get('source_selection', 'explicit' if request.get('source_root') else 'automatic')
    values['migration_policy'] = request.get('migration_policy', 'automatic')
    if values['source_selection'] not in {'automatic', 'explicit'} or values['migration_policy'] not in {'automatic', 'confirm'}:
        raise LauncherError('Geçersiz otomasyon seçimi.')
    values['automatic_ports'] = tuple(field for field in ('backend_port', 'frontend_port')
                                     if request.get(field) == 'auto')
    for field in PATH_FIELDS | TEXT_FIELDS:
        value = request.get(field) if field in fields else None
        if value is not None and (not isinstance(value, str) or len(value) > 8192 or any(c in value for c in '\0\r\n')):
            raise LauncherError('Geçersiz alan değeri.')
        values[field] = Path(value) if value and field in PATH_FIELDS else value or None
    for field in ('backend_port', 'frontend_port'):
        raw = request.get(field) if action in {'provision', 'ensure'} else None
        if raw == 'auto':
            raw = None
        value = int(raw) if raw not in ('', None) else None
        if value is not None and not 1 <= value <= 65535:
            raise LauncherError('Geçersiz port.')
        values[field] = value
    return argparse.Namespace(**values)


from scripts.launcher.runtime_selection import _python_choice, _node_choice, tool_choices as _tool_choices


def _bundled_tools(args, emit, *, project=None):
    """Runtime archives ship beside EXE; package indexes need not host CPython."""
    from scripts.launcher.installation import source_settings
    from scripts.launcher.installation_profiles import installation_home
    from scripts.launcher.installation_state import installation_lock
    from scripts.launcher.toolchain import ensure_toolchain
    options = _tool_choices(args)
    preparation_options = {**options, 'progress': getattr(args, 'progress', None)}
    if getattr(sys, 'frozen', False):
        args.runtime_dirs = (Path(sys.executable).parent,)
    settings = source_settings(args, project)
    if project is not None:
        from scripts.launcher.installation_bundle import require_bundle_host_runtimes
        require_bundle_host_runtimes(project, settings, **options)
    if options.get('python_executable'):
        emit({'type': 'phase', 'message': 'Sistem Python 3.11 x64 kullanılıyor; Python kurulmayacak'})
    if options.get('node_executable'):
        emit({'type': 'phase', 'message': 'Sistem Node.js kullanılıyor; Node.js arşivi indirilmeyecek'})
    emit({'type': 'phase', 'message': 'Seçilen runtime ve Node/npm hazırlanıyor'})
    with installation_lock(installation_home()):
        ensure_toolchain(installation_home(), settings, **preparation_options)


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
    from scripts.launcher.installation_sources import ArtifactDownloadError
    from scripts.launcher.installation_bundle import BundleHostRuntimeError
    from scripts.launcher.toolchain import RuntimeValidationError
    from scripts.launcher.system_node import SystemNodeError
    from scripts.launcher.system_python import SystemPythonError
    from scripts.launcher.installation_permissions import PermissionCheckError
    from scripts.launcher.resource_locks import ResourceLockError
    from scripts.launcher.installation_dependencies import (PackageCommandError, PackageTimeoutError,
                                                          VirtualEnvironmentError, VirtualEnvironmentRepairError)
    from scripts.build_manager import ManagerBuildError
    from scripts.launcher.installation_connection import ConnectionError
    from scripts.launcher.certificates import PackageTrustError
    from scripts.launcher.installation_readiness import StartupReadinessError
    from scripts.launcher.package_cache import PackageCacheError
    from .payload import ProductionSourceNotPrepared
    from scripts.launcher.installation_profiles import TLSFileError
    if isinstance(error, (PackageTrustError, StartupReadinessError, PackageCacheError, ProductionSourceNotPrepared, TLSFileError)):
        return error.code, str(error)
    if isinstance(error, ConnectionError):
        return error.code, str(error)
    if isinstance(error, (SystemPythonError, SystemNodeError, ArtifactDownloadError, BundleHostRuntimeError, RuntimeValidationError, PermissionCheckError, ResourceLockError, PackageCommandError, PackageTimeoutError, VirtualEnvironmentError, VirtualEnvironmentRepairError, ManagerBuildError)):
        return error.code, str(error)
    if isinstance(error, UnicodeError):
        return 'process_output_invalid', 'Alt süreç çıktısının karakter kodlaması okunamadı.'
    if isinstance(error, OSError):
        return _system_failure(error)
    if not isinstance(error, LauncherError):
        return 'operation_failed', 'İşlem tamamlanamadı; yapılandırma veya sistem erişimi doğrulanamadı.'
    text = str(error).casefold()
    categories = (
        (('windows manager paketi gerekli',), 'manager_distribution_required', 'Tam çevrimdışı paket için aynı sürümün Windows Manager dağıtımı gerekli.'),
        (('paket hedefi bir klasör',), 'bundle_output_invalid', 'Paket hedefi mevcut bir dosya; dosyanın üzerine yazılmadı.'),
        (('installation bundle output must be new',), 'bundle_output_invalid', 'Paket hedefi kaynak dizininin dışında yeni bir klasör olmalı; mevcut dosyalar korunuyor.'),
        (('installation bundle output must be outside all input',), 'bundle_output_invalid', 'Paket hedefi kaynak, Manager dağıtımı, asset ve bağımlılık girdilerinden ayrı olmalı.'),
        (('symlink', 'reparse'), 'storage_path_unsafe', 'Kurulum veya paket yolu bağlantı / reparse noktası içeriyor; güvenli bir yerel klasör gerekli.'),
        (('project root', 'manage.py was not found', 'vue package.json'), 'source_unavailable', 'Proje kaynağı bulunamadı veya Django/Vue kaynakları eksik. ZIP paketinin tamamını çıkarıp kaynak dizinini kontrol edin.'),
        (('uygulamak için kur ve başlat',), 'env_import_required', 'Seçilen .env profilin kayıtlı ayarlarından farklı. Uygulamak için Kur ve başlat kullanın.'),
        (('.env', 'environment file is invalid'), 'env_file_invalid', 'Seçilen .env okunamadı, biçimi veya profil ile uyumu doğrulanamadı. Dosyayı ve mevcut anahtar/veri yolu uyumunu kontrol edin.'),
        (('venv farklı',), 'venv_python_mismatch', 'Mevcut .venv seçilen Python’a bağlı değil; otomatik değiştirilmedi. Ayrı temiz kaynak dizini kullanın.'),
        (('uygun sistem python',), 'system_python_missing', 'Uygun sistem Python 3.11 x64 bulunamadı; Python komutu / yolu alanına python veya python.exe yolunu girin ya da “Python çalışma zamanını kur” seçeneğini işaretleyin.'),
        (('yalnız windows',), 'windows_required', 'Bu kurulum işlemi Windows x64 gerektirir.'),
        (('sha-256', 'checksum', 'hash', 'integrity', 'differ', 'değişmiş'), 'integrity_failed', 'Dosya bütünlüğü doğrulanamadı; değiştirilmiş paket kullanılmadı.'),
        (('tls', 'certificate', 'certification', 'ssl'), 'tls_failed', 'TLS sertifikası veya güvenli bağlantı doğrulanamadı.'),
        (('python artifact unavailable',), 'python_runtime_missing', 'Doğrulanmış Python runtime arşivi bulunamadı.'),
        (('node artifact unavailable', 'npm artifact unavailable'), 'runtime_missing', 'Doğrulanmış Node/npm runtime arşivi bulunamadı.'),
        (('kilitli python', 'python paket', 'locked python wheels'), 'python_packages_missing', 'Kilitli Python paketleri seçilen kaynaklardan edinilemedi.'),
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

def _system_failure(error):
    """Keep actionable OS codes without filenames, command lines or OS text."""
    number, winerror = error.errno, getattr(error, 'winerror', None)
    if number in {errno.EACCES, errno.EPERM} or winerror in {5, 32, 33}:
        code, message = 'system_access_denied', 'Dosya veya süreç erişimi engellendi ya da dosya başka bir işlemde açık.'
    elif number == errno.ENOSPC or winerror == 112:
        code, message = 'system_disk_full', 'İşlem için yeterli disk alanı yok.'
    elif number == errno.ENAMETOOLONG or winerror == 206:
        code, message = 'system_path_too_long', 'Dosya yolu Windows uzunluk sınırını aşıyor.'
    elif number == errno.ENOENT or winerror in {2, 3}:
        code, message = 'system_path_missing', 'Gerekli dosya, klasör veya çalıştırılabilir araç bulunamadı.'
    else:
        code, message = 'system_io_failed', 'Dosya veya alt süreç işlemi tamamlanamadı.'
    for label, value in (('WinError', winerror), ('errno', number)):
        if type(value) is int and value > 0:
            message += f' {label}: {value}.'
    return code, message


def execute(request, emit, admin_provider, stop, migration_provider=None):
    """Map only declared results/errors; a failure belongs to this worker alone."""
    phase = 'Hazırlık'
    try:
        if not isinstance(request, dict) or request.get('action') not in ACTION_LABELS:
            raise LauncherError('Geçersiz işlem.')
        args = arguments(request)
        if getattr(sys, 'frozen', False):
            args.runtime_dirs = (Path(sys.executable).parent,)
        from .paths import default_source_root
        args.source_root = request.get('source_root') or str(default_source_root())
        args.admin_provider = admin_provider
        args.migration_provider = migration_provider
        args.manager_repair_venv = True
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
        remedies = {
            'process_output_invalid': 'Güncel Manager ile yeniden deneyin; mevcut ortam ve tamamlanan kurulum aşamaları korunur.',
            'system_access_denied': 'Bu kaynak dizinini kullanan diğer AW Center işlemlerini kapatıp yeniden deneyin. Devam ederse klasör yazma izinlerini ve güvenlik yazılımının kaydını kontrol edin; ortamı silmeyin.',
            'system_disk_full': 'Kurulum ve Windows geçici dosya diskinde boş alan açıp yeniden deneyin; tamamlanan aşamalar korunur.',
            'system_path_too_long': 'Proje ZIP paketini daha kısa bir yerel yola çıkarıp bu kaynağı seçin; mevcut profil ve veritabanını silmeyin.',
            'system_path_missing': 'ZIP paketinin tamamının çıkarıldığını ve seçilen Python/Node dosyalarının mevcut olduğunu kontrol edip yeniden deneyin.',
            'system_io_failed': 'Rapordaki son aşama ve sayısal sistem kodunu kullanarak disk veya çalıştırma erişimini kontrol edin; tamamlanan aşamalar korunur.',
            'port_unavailable': 'Gelişmiş ayarlarda ilgili yerel port için auto yazın veya boş bir port seçin. Başka uygulamalar otomatik kapatılmaz.',
            'connection_override_invalid': 'Gelişmiş bağlantı ayarlarını ve varsa özel .env içindeki origin/reset/invitation adreslerini birlikte kontrol edin.',
            'manager_distribution_required': 'Aynı sürümden Windows Manager ZIP paketinin tamamını çıkarın. Kaynak çalıştırmada Windows Manager paketi alanını seçin; EXE ile açıldığında dağıtım otomatik bulunur.',
            'bundle_output_invalid': 'Çıktı için bir klasör seçin veya alanı boş bırakın; mevcut dosyalar korunarak yeni bir paket dizini oluşturulur.',
            'storage_path_unsafe': 'Bağlantı / junction içermeyen yerel bir klasör kullanın. Mevcut profil ve veritabanını silmeyin.',
            'source_unavailable': 'ZIP paketinin yalnız EXE dosyasını değil tamamını çıkarın. Proje kaynak dizininde backend ve frontend klasörlerinin bulunduğunu kontrol edin.',
            'python_packages_missing': 'İzin verilen paket kaynakları denendi. Kısıtlı bilgisayara tam çevrimdışı Manager paketini aktarın veya erişilebilir Python paket indeksini seçin.',
            'npm_packages_missing': 'İzin verilen paket kaynakları denendi. Tam çevrimdışı Manager paketini aktarın veya erişilebilir npm deposunu seçin.',
            'system_python_missing': 'Çalışma sekmesindeki gelişmiş ayarlarda Python komutu / yolu alanına python, py -3.11 veya python.exe dosyasının tam yolunu girin. CPython 3.11 x64 gerekir; isterseniz Python kurulumu kutusunu seçin.',
            'env_import_required': 'Çalışan ilgili görevi durdurun; seçilen dosyayı Kur ve başlat ile uygulayın. Mevcut anahtar ve veri yolları korunmalıdır.',
            'env_file_invalid': 'Çalışma sekmesindeki .env dosyasını kontrol edin; yalnız uygulama ayarlarını içeren, profilin anahtarları ve veri yollarıyla uyumlu bir dosya seçin.',
        }
        from scripts.launcher.installation_sources import ArtifactDownloadError
        from scripts.launcher.installation_bundle import BundleHostRuntimeError
        from scripts.launcher.toolchain import RuntimeValidationError
        from scripts.launcher.system_node import SystemNodeError
        from scripts.launcher.system_python import SystemPythonError
        from scripts.launcher.installation_permissions import PermissionCheckError
        from scripts.launcher.resource_locks import ResourceLockError
        from scripts.launcher.installation_dependencies import (PackageCommandError, PackageTimeoutError,
                                                              VirtualEnvironmentError, VirtualEnvironmentRepairError)
        from scripts.build_manager import ManagerBuildError
        from scripts.launcher.certificates import PackageTrustError
        from scripts.launcher.installation_readiness import StartupReadinessError
        from scripts.launcher.package_cache import PackageCacheError
        from .payload import ProductionSourceNotPrepared
        from scripts.launcher.installation_profiles import TLSFileError
        remedy = error.remedy if isinstance(error, (SystemPythonError, SystemNodeError, ArtifactDownloadError, BundleHostRuntimeError, RuntimeValidationError, PermissionCheckError, ResourceLockError, PackageCommandError, PackageTimeoutError, VirtualEnvironmentError, VirtualEnvironmentRepairError, ManagerBuildError, PackageTrustError, StartupReadinessError, PackageCacheError, ProductionSourceNotPrepared, TLSFileError)) else remedies.get(code, _remedy(phase))
        event = {'type': 'error', 'code': code, 'message': f'{phase}: {reason}', 'remedy': remedy}
        if getattr(error, 'field', None) in PATH_FIELDS | TEXT_FIELDS | {'backend_port', 'frontend_port', 'profile'}:
            event['field'] = error.field
        emit(event)
        emit({'type': 'done', 'ok': False})


def _project_for(action, args):
    from scripts.launcher.discovery import discover_project
    from scripts.launcher.installation import require_windows
    from scripts.launcher.installation_profiles import installation_home
    args.progress('Proje kaynağı ve paket bütünlüğü doğrulanıyor')
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


def _manager_distribution(source, args):
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).parent
    if args.manager_distribution:
        return Path(args.manager_distribution)
    for candidate in dict.fromkeys((source.parent, source)):
        if (candidate / 'AWCenterManager.exe').is_file() and (candidate / 'manager-manifest.json').is_file():
            return candidate
    return None


def _bundle_output(args, home, source):
    from .paths import new_bundle_output
    from scripts.launcher.installation_permissions import require_unlinked
    from scripts.launcher.installation import source_settings
    from scripts.launcher.installation_bundle import bundle_input_roots
    output = args.output or new_bundle_output(home / 'exports')
    require_unlinked(output)
    if output.exists():
        if not output.is_dir():
            raise LauncherError('Paket hedefi bir klasör olmalı; mevcut dosyaya yazılmadı.')
        output = new_bundle_output(output)
    inputs = (source, *bundle_input_roots(source_settings(args), assets=args.assets,
                                         manager_distribution=_manager_distribution(source, args)))
    roots = tuple(Path(os.path.abspath(root)) for root in inputs)
    if any(Path(os.path.abspath(output)).is_relative_to(root) for root in roots):
        output = new_bundle_output(home / 'exports')
        if any(output.is_relative_to(root) for root in roots):
            raise LauncherError('installation bundle output must be outside all input directories')
        args.progress('Paket hedefi girdilerle çakışıyor; %LOCALAPPDATA%\\AWCenter\\exports altında yeni hedef seçildi')
    return output


def _dispatch(action, args, emit):
    if action in {'ensure', 'provision', 'start', 'bundle'} and not getattr(args, '_storage_prepared', False):
        from scripts.launcher.installation_profiles import installation_home
        from scripts.launcher.installation_state import prepare_installation_storage
        prepare_installation_storage(installation_home(), progress=args.progress)
        args._storage_prepared = True
    if action == 'ensure':
        from .ensure import run
        return run(args, emit)
    if action in {'start', 'doctor'}:
        # Match inspection/ensure: updated media is not a new installed profile.
        # Resolve before start's leases so they protect the recorded source.
        from .ensure import resolve_source
        resolve_source(args)
    if action in {'provision', 'start', 'bundle'}:
        from scripts.launcher.resource_locks import path_claims, resource_locks
        from scripts.launcher.installation_profiles import installation_home
        args.progress('Kurulum alanı ve işlem kilitleri denetleniyor')
        home, source = installation_home(), Path(args.source_root).absolute()
        # A selected canonical release is also the mutable destination. Claim
        # it upfront: leases deliberately never upgrade an existing read claim.
        mutable_source = args.profile == 'dev' or any(
            source.is_relative_to(home / name) for name in ('releases', 'r'))
        claims = path_claims(source, write=action == 'provision' and mutable_source)
        if action == 'bundle':
            args.output = _bundle_output(args, home, source)
            claims.update(path_claims(args.output, write=True))
        else:
            claims.update({'profile:' + args.profile: True, 'runtime': action == 'provision'})
        with resource_locks(home, claims):
            return _dispatch_claimed(action, args, emit)
    return _dispatch_claimed(action, args, emit)


def _dispatch_claimed(action, args, emit):
    if action == 'inspect':
        from .inspection import inspect_profile
        inspect_profile(args, emit)
        return
    if action == 'test-sources':
        from .source_checks import run
        run(args, emit)
        return
    project = _project_for(action, args)
    if args.env_file and action in {'start', 'doctor'}:
        from scripts.launcher.installation_profiles import load_profile
        from scripts.launcher.installation_env import check_selected_environment
        check_selected_environment(project, load_profile(project, args.profile), args.env_file)
    if action == 'doctor':
        from scripts.launcher.installation import doctor
        emit({'type': 'checks', 'checks': doctor(project, args.profile)})
    elif action == 'bundle':
        _bundle(project, args, emit)
    else:
        _lifecycle(project, action, args, emit)


def _bundle(project, args, emit):
    from scripts.launcher.installation import source_settings
    from .distribution import prepare_full_manager
    args.progress('Windows Manager dağıtımı ve paket hedefi doğrulanıyor')
    distribution = _manager_distribution(project.root, args)
    args.progress('Tam çevrimdışı Manager paketi hazırlanıyor')
    prepare_full_manager(project, args.output, source_settings(args, project), distribution,
                         assets=args.assets, feature_catalog=args.feature_catalog)
    from scripts.launcher.installation_profiles import installation_home
    # Show the known destination without recording the operator's home path.
    local = os.environ.get('LOCALAPPDATA')
    exports = installation_home() / 'exports' if local else None
    detail = (f'%LOCALAPPDATA%\\AWCenter\\exports\\{args.output.name}'
              if exports is not None and args.output.parent == exports else
              f'Seçilen çıktı klasöründe hazır: {args.output.name}')
    emit({'type': 'checks', 'checks': [{'name': 'Çevrimdışı paket', 'status': 'ready', 'detail': detail}]})


def _lifecycle(project, action, args, emit):
    from scripts.launcher.resource_locks import lifecycle_locks
    from scripts.launcher.installation_profiles import installation_home
    with lifecycle_locks(installation_home(), project, args.profile, write=action == 'provision'):
        _run_lifecycle(project, action, args, emit)


def _run_lifecycle(project, action, args, emit, *, ensured=False):
    if getattr(args, 'manager_ensure', False) and not ensured:
        from .ensure import claimed
        return claimed(project, action, args, emit)
    from scripts.launcher.installation import provision, start_profile
    if action == 'provision':
        if args.env_file:
            from scripts.launcher.installation_env import read_selected_environment
            read_selected_environment(project, args.profile, args.env_file)
        if getattr(sys, 'frozen', False):
            args.runtime_dirs = (Path(sys.executable).parent,)
        emit({'type': 'checks', 'checks': provision(project, args)})
    args.progress('Uygulama ve worker süreçleri başlatılıyor')
    def ready(profile):
        check_cancelled()
        url = (f"https://{profile['host']}:{profile['backend_port']}/app/" if profile['name'] == 'prod' else
               f"http://{profile['host']}:{profile['frontend_port']}/app/")
        emit({'type': 'ready', 'url': url})
    def lifecycle_event(event):
        if event.get('type') == 'phase':
            args.progress(event['message'])
        else:
            emit(event)
    start_profile(project, args.profile, on_ready=ready, on_health=lifecycle_event)
