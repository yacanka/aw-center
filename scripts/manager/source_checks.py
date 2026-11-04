"""Read-only source diagnostics, independent of provisioning and runtime startup."""
from pathlib import Path
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


def _remote_checks(settings):
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
    endpoints = []
    if settings.mode == 'online':
        endpoints.extend([('PyPI', 'https://pypi.org/simple/'), ('npm', 'https://registry.npmjs.org/-/ping')])
    endpoints.extend((name, url) for name, url in (
        ('Kurumsal Python', settings.python_index_url), ('Kurumsal npm', settings.npm_registry_url),
        ('Runtime deposu', str(settings.repository) if settings.repository and str(settings.repository).startswith('https://') else None)) if url)
    proxies = getproxies()
    opener = build_opener(_SecureRedirect(), ProxyHandler(proxies), HTTPSHandler(context=context))
    checks = []
    for name, url in endpoints:
        check_cancelled()
        status, detail = _probe(url, opener, proxies)
        checks.append({'name': name, 'status': status, 'detail': detail})
    return checks


def run(args, emit):
    from scripts.launcher.installation import source_settings
    settings = source_settings(args)
    checks = []
    local_source = settings.offline_dir or (settings.repository and not str(settings.repository).startswith('https://'))
    if settings.mode == 'offline' or local_source:
        from scripts.launcher.installation_dependencies import _offline_dependencies
        source = _offline_dependencies(discover_project(Path(args.source_root)), settings)
        checks.append({'name': 'Offline paket', 'status': 'ready' if source else 'missing',
                       'detail': 'Kilitli bağımlılık envanteri doğrulandı.' if source else 'Doğrulanmış bağımlılık paketi seçin.'})
    if settings.mode != 'offline':
        checks.extend(_remote_checks(settings))
        if not checks:
            checks.append({'name': 'Kaynaklar', 'status': 'missing', 'detail': 'Kurumsal paket adreslerini veya yerel offline paketi seçin.'})
    emit({'type': 'checks', 'checks': checks})
