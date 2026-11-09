"""Read-only source diagnostics, independent of provisioning and runtime startup."""
from pathlib import Path
import json
import re
import socket
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit

from scripts.launcher.discovery import discover_project
from scripts.launcher.model import LauncherError
from scripts.launcher.installation_sources import _https_url
from scripts.launcher.process import OperationCancelled, check_cancelled


def _http_failure(code, *, proxy=False):
    if code == 407:
        return 'Proxy kimlik doğrulaması gerekli (HTTP 407). Kurumsal proxy oturumunu ve erişim ayarlarını kontrol edin.'
    if proxy:
        return f'Proxy HTTPS tüneli kurulamadı (HTTP {code}). Proxy erişim izinlerini ve hedef depo adresini kontrol edin.'
    remedies = {
        401: 'Depo kimlik doğrulaması istiyor; kurumsal depo erişim ayarlarını kontrol edin.',
        403: 'Depoya erişim reddedildi; kullanıcı ve ağ erişim izinlerini kontrol edin.',
        404: 'Depo adresi bulunamadı; paket kaynağının tam adresini kontrol edin.',
    }
    remedy = remedies.get(code, 'Depo adresini ve HTTP erişim ayarlarını kontrol edin.')
    if isinstance(code, int) and 500 <= code <= 599:
        remedy = 'Depo veya ağ geçidi sunucu hatası döndürdü; servis durumunu kontrol edip yeniden deneyin.'
    return f'HTTP {code}: {remedy}'


def _connection_failure(error, *, using_proxy):
    """Classify transport failures without returning exception/proxy payloads."""
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, ssl.SSLCertVerificationError):
        return 'CA / sertifika doğrulaması başarısız. Güvenilen CA zincirini, sertifikanın geçerlilik süresini ve depo adresiyle uyumunu kontrol edin.'
    if isinstance(reason, ssl.SSLError):
        return 'TLS bağlantısı kurulamadı. Sunucunun veya kurumsal proxy\'nin TLS yapılandırmasını kontrol edin.'
    # CPython exposes HTTPS CONNECT status only inside this OSError message.
    tunnel = re.match(r'^Tunnel connection failed: ([0-9]{3})\b', str(reason)) if isinstance(reason, OSError) else None
    if tunnel:
        return _http_failure(int(tunnel[1]), proxy=True)
    if using_proxy:
        return 'Proxy üzerinden bağlantı kurulamadı. Proxy adresini, ağ erişimini ve zaman aşımı ayarlarını kontrol edin.'
    if isinstance(reason, TimeoutError):
        return 'Bağlantıda zaman aşımı oluştu. Ağ erişimini ve depo servisinin durumunu kontrol edin.'
    if isinstance(reason, socket.gaierror):
        return 'DNS çözümlemesi başarısız. Depo adresini, kurumsal ağ/VPN bağlantısını ve DNS ayarlarını kontrol edin.'
    return 'Bağlantı kurulamadı. Ağ/VPN bağlantısını, güvenlik duvarını ve depo servisinin erişilebilirliğini kontrol edin.'


def _probe(url, opener, proxies):
    from urllib.request import proxy_bypass
    using_proxy = False
    try:
        _https_url(url)
        using_proxy = bool(proxies.get('https') and not proxy_bypass(urlsplit(url).netloc))
        with opener.open(url, timeout=10) as response:
            if response.status == 200:
                return 'available', 'HTTPS bağlantısı ve sertifika doğrulaması başarılı; paket kapsamı kurulumda doğrulanır.'
            return 'missing', _http_failure(response.status)
    except OperationCancelled:
        raise
    except HTTPError as error:
        try:
            return 'missing', _http_failure(error.code)
        finally:
            error.close()
    except (URLError, OSError) as error:
        return 'missing', _connection_failure(error, using_proxy=using_proxy)
    except LauncherError:
        return 'missing', 'Kaynak adresi geçersiz. Kullanıcı bilgisi veya token içermeyen bir HTTPS depo adresi kullanın.'
    except Exception:
        return 'missing', 'Kaynak kontrolü tamamlanamadı. Depo yapılandırmasını kontrol edip yeniden deneyin.'


def _remote_checks(settings, project=None):
    from scripts.launcher.installation_sources import _SecureRedirect
    from urllib.request import HTTPSHandler, ProxyHandler, build_opener, getproxies
    try:
        # On Windows this includes the OS CA/ROOT stores, plus OpenSSL defaults.
        context = ssl.create_default_context()
    except (OSError, ValueError):
        return [{'name': 'Sistem CA', 'status': 'missing',
                 'detail': 'İşletim sisteminin varsayılan güven deposu yüklenemedi. Sistem sertifikalarını ve TLS ortam ayarlarını kontrol edin.'}]
    if settings.ca_file:
        try:
            context.load_verify_locations(cafile=str(settings.ca_file))
        except (OSError, ValueError):
            return [{'name': 'CA dosyası', 'status': 'missing',
                     'detail': 'Seçilen CA dosyası okunamadı veya geçerli bir PEM CA paketi değil. Dosyanın mevcut, okunabilir ve PEM biçiminde olduğunu kontrol edin.'}]
    from scripts.launcher.installation_sources import acquisition_urls, load_catalog
    from urllib.parse import quote
    endpoints = []
    python_package = 'django'
    npm_package = 'vue'
    if project is not None:
        locks = json.loads((project.frontend / 'package-lock.json').read_text(encoding='utf-8'))
        package = next(((name.removeprefix('node_modules/'), value['version'])
                        for name, value in locks.get('packages', {}).items()
                        if name.startswith('node_modules/') and value.get('version')), None)
        if package:
            npm_package = quote(package[0], safe='') + '/' + quote(package[1], safe='')
        match = re.search(r'^([a-zA-Z0-9_.-]+)==', project.requirements.read_text(encoding='utf-8'), re.MULTILINE)
        if match:
            python_package = match[1].lower().replace('_', '-')
    for base in acquisition_urls(settings, 'https://pypi.org/simple', settings.python_index_url):
        endpoints.append(('Python wheel indeksi (örnek paket)', base.rstrip('/') + '/' + python_package + '/'))
    for base in acquisition_urls(settings, 'https://registry.npmjs.org', settings.npm_registry_url):
        endpoints.append(('npm kilitli paket (örnek)', base.rstrip('/') + '/' + npm_package))
    repository = str(settings.repository) if settings.repository and str(settings.repository).startswith('https://') else None
    for artifact in load_catalog().values():
        selected = repository.rstrip('/') + '/' + artifact.filename if repository else None
        for url in acquisition_urls(settings, artifact.url, selected):
            endpoints.append((artifact.name + ' runtime arşivi', url))
            if repository and url == selected:
                endpoints.append((artifact.name + ' runtime arşivi (runtimes)', repository.rstrip('/') + '/runtimes/' + artifact.filename))
    proxies = getproxies()
    opener = build_opener(_SecureRedirect(), ProxyHandler(proxies), HTTPSHandler(context=context))
    checks = []
    for name, url in endpoints:
        check_cancelled()
        status, detail = _probe(url, opener, proxies)
        if status == 'available':
            status = 'unverified'
            detail = ('Örnek paket adresine erişildi; bu kontrol paket dosyalarının indirme erişimini doğrulamaz. '
                      'Tüm paketlerin kapsamı ve hash doğrulaması kurulum veya çevrimdışı paket hazırlığında yapılır.'
                      if 'örnek' in name else
                      'Runtime arşivi adresine erişildi; dosyanın tamamı ve SHA-256 değeri indirme sırasında doğrulanır.')
        checks.append({'name': name, 'status': status, 'detail': detail})
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
        checks.extend(_remote_checks(settings, project))
        if not checks:
            checks.append({'name': 'Kaynaklar', 'status': 'missing', 'detail': 'Kurumsal paket adreslerini veya yerel offline paketi seçin.'})
    emit({'type': 'checks', 'checks': checks})
