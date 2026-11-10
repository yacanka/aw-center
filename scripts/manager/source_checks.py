"""Trace repository access through disposable downloads without provisioning."""
from pathlib import Path
import ssl
from urllib.parse import quote

from scripts.launcher.discovery import discover_project
from scripts.launcher.process import OperationCancelled, check_cancelled
from .source_packages import npm_file, npm_sample, python_file, python_sample
from .source_probe import ProbeClient, ProbeFailure, ProbeRedirect, verify_digest


def _stage(checks, settings, label, operation, success):
    check_cancelled()
    settings.report(label + ' başlıyor')
    try:
        result = operation()
        detail, status = success(result), 'ready'
    except OperationCancelled:
        raise
    except ProbeFailure as error:
        result = None
        detail = f'[{error.code}] {error}'
        status = 'unverified' if error.code == 'source_hash_missing' else 'blocked'
    except Exception:
        result, status = None, 'blocked'
        detail = '[source_probe_failed] Kaynak kontrolü tamamlanamadı. Depo yapılandırmasını kontrol edip yeniden deneyin.'
    checks.append({'name': label, 'status': status, 'detail': detail})
    settings.report(f'{label}: {detail}')
    return result


def _package_check(checks, settings, client, project, kind, base, label):
    try:
        sample = python_sample(project) if kind == 'Python' else npm_sample(project)
    except ProbeFailure as error:
        _stage(checks, settings, label + ' — kilitli örnek', lambda: _raise(error), str)
        return
    settings.report(f'{label}: örnek paket {sample.name}=={sample.version}; tüm bağımlılıkların kapsamı sınanmaz.')
    suffix = sample.name + '/' if kind == 'Python' else quote(sample.name, safe='@').replace('%2F', '%2f')
    url = base.rstrip('/') + '/' + suffix
    accept = ('application/vnd.pypi.simple.v1+json, application/vnd.pypi.simple.v1+html;q=0.9, text/html;q=0.8'
              if kind == 'Python' else 'application/vnd.npm.install-v1+json, application/json;q=0.8')
    metadata = _stage(checks, settings, label + ' — indeks / metadata erişimi',
                      lambda: client.metadata(url, accept=accept),
                      lambda value: f'HTTPS yanıtının tamamı okundu: {value.size} bayt. Örnek: {sample.name}=={sample.version}.')
    if metadata is None:
        return
    resolve = python_file if kind == 'Python' else npm_file
    selected = _stage(checks, settings, label + ' — kilitli sürüm çözümleme',
                      lambda: resolve(metadata, sample),
                      lambda _: f'Kilitli örnek sürümün gerçek dosya adresi bulundu: {sample.name}=={sample.version}.')
    if selected is None:
        return
    transfer = _stage(checks, settings, label + ' — paket indirme', lambda: client.download(selected.url),
                      lambda value: f'Örnek dosyanın tamamı geçici alana indirildi: {value.size} bayt; paket kurulmadı.')
    if transfer is not None:
        _stage(checks, settings, label + ' — dosya bütünlüğü', lambda: verify_digest(transfer, selected.expected),
               lambda algorithm: f'{algorithm.upper()} doğrulandı. Yalnız kilitli örnek dosya doğrulandı; tüm paketlerin kapsamı kurulum veya offline paket hazırlığında sınanır.')


def _raise(error):
    raise error


def _runtime_check(checks, settings, client, artifact, urls, label):
    def download():
        from scripts.launcher.installation_sources import MAX_ARTIFACT_BYTES
        for number, url in enumerate(urls):
            try:
                return client.download(url, limit=MAX_ARTIFACT_BYTES)
            except ProbeFailure as error:
                if not error.code.startswith('source_http_') or number + 1 == len(urls):
                    raise
                settings.report(f'{label}: [{error.code}] {error} '
                                'Aynı deponun runtimes dizinindeki izinli alternatif deneniyor.')
    transfer = _stage(checks, settings, label + ' — arşiv indirme', download,
                      lambda value: f'Runtime arşivinin tamamı geçici alana indirildi: {value.size} bayt; runtime kurulmadı.')
    if transfer is not None:
        _stage(checks, settings, label + ' — dosya bütünlüğü',
               lambda: verify_digest(transfer, {'sha256': (artifact.sha256,)}),
               lambda algorithm: f'{algorithm.upper()} değeri kaynakla gelen onaylı runtime kataloğuyla doğrulandı.')


def _remote_checks(settings, project, *, checks=None):
    from urllib.request import HTTPSHandler, ProxyHandler, build_opener, getproxies
    from scripts.launcher.installation_sources import acquisition_urls, load_catalog
    checks = [] if checks is None else checks
    try:
        # On Windows this includes the OS CA/ROOT stores, plus OpenSSL defaults.
        context = ssl.create_default_context()
    except (OSError, ValueError):
        checks.append({'name': 'Sistem CA', 'status': 'blocked',
                       'detail': 'İşletim sisteminin varsayılan güven deposu yüklenemedi. Sistem sertifikalarını ve TLS ortam ayarlarını kontrol edin.'})
        return checks
    if settings.ca_file:
        try:
            context.load_verify_locations(cafile=str(settings.ca_file))
        except (OSError, ValueError):
            checks.append({'name': 'CA dosyası', 'status': 'blocked',
                           'detail': 'Seçilen CA dosyası okunamadı veya geçerli bir PEM CA paketi değil. Dosyanın mevcut, okunabilir ve PEM biçiminde olduğunu kontrol edin.'})
            return checks
    proxies = getproxies()
    opener = build_opener(ProbeRedirect(settings.report, proxies), ProxyHandler(proxies), HTTPSHandler(context=context))
    client = ProbeClient(opener, proxies, settings.report)
    for kind, public, selected in (('Python', 'https://pypi.org/simple', settings.python_index_url),
                                   ('npm', 'https://registry.npmjs.org', settings.npm_registry_url)):
        urls = acquisition_urls(settings, public, selected)
        for number, url in enumerate(urls):
            _package_check(checks, settings, client, project, kind, url, f'{kind} kaynak {number + 1}/{len(urls)}')
    repository = str(settings.repository) if settings.repository and str(settings.repository).startswith('https://') else None
    for artifact in load_catalog().values():
        selected = repository.rstrip('/') + '/' + artifact.filename if repository else None
        urls = acquisition_urls(settings, artifact.url, selected)
        for number, url in enumerate(urls):
            candidates = [url]
            if repository and url == selected:
                candidates.append(repository.rstrip('/') + '/runtimes/' + artifact.filename)
            _runtime_check(checks, settings, client, artifact, candidates,
                           f'{artifact.name} runtime kaynak {number + 1}/{len(urls)}')
    return checks


def run(args, emit):
    from scripts.launcher.installation import source_settings
    settings = source_settings(args)
    project = discover_project(Path(args.source_root))
    checks = []
    local_source = settings.offline_dir or (settings.repository and not str(settings.repository).startswith('https://'))
    if settings.mode == 'offline' or local_source:
        from scripts.launcher.installation_dependencies import _offline_dependencies
        source = _offline_dependencies(project, settings)
        for label in ('Python wheel paketi', 'npm cache paketi'):
            checks.append({'name': label, 'status': 'ready' if source else 'missing',
                           'detail': 'Kilitli bağımlılık envanteri doğrulandı.' if source else 'Doğrulanmış bağımlılık paketi seçin.'})
    from scripts.launcher.installation_sources import load_catalog, _verify
    roots = list(settings.runtime_dirs)
    if settings.offline_dir:
        roots.append(settings.offline_dir)
    if settings.repository and not str(settings.repository).startswith('https://'):
        roots.append(Path(settings.repository))
    for artifact in load_catalog().values():
        files = [base / relative / artifact.filename for base in roots for relative in ('', 'runtimes')]
        candidate = next((path for path in files if path.exists()), None)
        if candidate:
            _verify(candidate, artifact)
        if candidate or settings.mode == 'offline':
            checks.append({'name': artifact.name + ' yerel runtime', 'status': 'ready' if candidate else 'missing',
                           'detail': 'SHA-256 doğrulandı.' if candidate else 'Yerel arşiv yok; uyumlu sistem aracı varsa kullanılabilir.'})
    if settings.mode != 'offline':
        try:
            _remote_checks(settings, project, checks=checks)
        except OperationCancelled:
            if checks:
                emit({'type': 'checks', 'checks': checks})
            raise
        if not checks:
            checks.append({'name': 'Kaynaklar', 'status': 'missing', 'detail': 'Kurumsal paket adreslerini veya yerel offline paketi seçin.'})
    emit({'type': 'checks', 'checks': checks})
