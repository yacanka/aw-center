"""Bounded, disposable HTTPS transfers for Manager repository diagnostics."""
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
import errno
import hashlib
import hmac
from http.client import HTTPException, IncompleteRead
import io
from pathlib import Path
import re
import socket
import ssl
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request

from scripts.launcher.installation_sources import _SecureRedirect, _https_url
from scripts.launcher.model import LauncherError
from scripts.launcher.process import OperationCancelled, check_cancelled

METADATA_LIMIT = 8 * 1024 * 1024
PACKAGE_LIMIT = 128 * 1024 * 1024
REQUEST_TIMEOUT = 10
TRANSFER_TIMEOUT = 120


class ProbeFailure(Exception):
    """Only reviewed messages and codes cross the private diagnostic boundary."""

    def __init__(self, code, detail):
        self.code = code
        super().__init__(detail)


def _storage_failure(error):
    if error.errno == errno.ENOSPC:
        return ProbeFailure('source_storage_full', 'Geçici indirme alanında disk dolu; boş alan açıp denetimi yeniden çalıştırın.')
    if error.errno in {errno.EACCES, errno.EPERM} or getattr(error, 'winerror', None) in {5, 32, 33}:
        return ProbeFailure('source_storage_access_denied', 'Geçici indirme dosyasına erişim engellendi; kullanıcı izinlerini ve dosya kilitlerini kontrol edin.')
    return ProbeFailure('source_storage_failed', 'Geçici indirme dosyası oluşturulamadı veya yazılamadı; geçici dizin erişimini ve diski kontrol edin.')


@contextmanager
def _storage_cleanup():
    cleanup = ExitStack()
    try:
        yield cleanup
    finally:
        try:
            cleanup.close()
        except OSError as error:
            raise _storage_failure(error) from None


def http_failure(code, *, proxy=False):
    remedies = {
        400: 'İstek reddedildi; paket yöneticisine ait depo API adresini ve proxy kurallarını kontrol edin.',
        401: 'Depo kimlik doğrulaması istiyor; kurumsal depo erişimini kontrol edin.',
        403: 'Depoya veya dosya sunucusuna erişim reddedildi; ağ/proxy erişim izinlerini kontrol edin.',
        404: 'Adres veya kilitli paket dosyası bulunamadı; depo adresini ve paket kapsamını kontrol edin.',
        407: 'Proxy kimlik doğrulaması gerekli; kurumsal proxy oturumunu ve erişim ayarlarını kontrol edin.',
    }
    detail = remedies.get(code, 'Depo adresini ve HTTP erişim ayarlarını kontrol edin.')
    if 300 <= code < 400:
        detail = 'HTTPS yönlendirmesi tamamlanamadı; yönlendirme döngüsünü veya depo adresini kontrol edin.'
    if 500 <= code < 600:
        detail = 'Depo veya ağ geçidi sunucu hatası döndürdü; servis durumunu kontrol edip yeniden deneyin.'
    prefix = 'Proxy HTTPS tüneli kurulamadı. ' if proxy and code != 407 else ''
    return ProbeFailure(f'source_http_{code}', f'HTTP {code}: {prefix}{detail}')


def connection_failure(error, *, using_proxy=False):
    reason = error.reason if isinstance(error, URLError) else error
    if isinstance(reason, ssl.SSLCertVerificationError):
        return ProbeFailure('source_tls_failed', 'CA / sertifika doğrulaması başarısız. Güvenilen CA zincirini, sertifika geçerliliğini ve sunucu adı uyumunu kontrol edin.')
    if isinstance(reason, ssl.SSLError):
        return ProbeFailure('source_tls_failed', 'TLS bağlantısı kurulamadı. Sunucunun veya kurumsal proxy TLS yapılandırmasını kontrol edin.')
    tunnel = re.match(r'^Tunnel connection failed: ([0-9]{3})\b', str(reason)) if isinstance(reason, OSError) else None
    if tunnel:
        return http_failure(int(tunnel[1]), proxy=True)
    route = ' Proxy adresini ve proxy üzerinden hedef erişimini de kontrol edin.' if using_proxy else ''
    if isinstance(reason, TimeoutError):
        return ProbeFailure('source_timeout', 'Bağlantıda veya veri aktarımında zaman aşımı oluştu. Ağ erişimini ve sunucu durumunu kontrol edin.' + route)
    if isinstance(reason, socket.gaierror):
        return ProbeFailure('source_dns_failed', 'DNS çözümlemesi başarısız. Depo/dosya sunucusu adresini, DNS ve ağ/VPN bağlantısını kontrol edin.' + route)
    return ProbeFailure('source_connection_failed', 'Bağlantı kurulamadı veya kesildi. Ağ/VPN, güvenlik duvarı ve dosya sunucusu erişimini kontrol edin.' + route)


def checked_url(url):
    try:
        if not isinstance(url, str) or len(url) > 8192 or any(ord(char) <= 32 for char in url):
            raise ValueError
        _https_url(url, allow_query=True)
        urlsplit(url).port
    except (LauncherError, ValueError):
        raise ProbeFailure('source_url_invalid', 'Kaynak veya yönlendirme adresi geçersiz. Kullanıcı bilgisi içermeyen güvenli bir HTTPS adresi gerekli.') from None
    return url


def host_label(url):
    """Expose only a validated hostname, never URL paths, credentials or queries."""
    hostname = urlsplit(checked_url(url)).hostname
    try:
        label = hostname.encode('idna').decode('ascii')
    except UnicodeError:
        raise ProbeFailure('source_url_invalid', 'Kaynak sunucusunun adı geçersiz.') from None
    if len(label) > 253 or not re.fullmatch(r'[A-Za-z0-9.:-]+', label):
        raise ProbeFailure('source_url_invalid', 'Kaynak sunucusunun adı geçersiz.')
    return label


def _using_proxy(url, proxies):
    from urllib.request import proxy_bypass
    return bool(proxies.get('https') and not proxy_bypass(urlsplit(url).netloc))


def _route_label(url, proxies):
    return 'kurumsal proxy' if _using_proxy(url, proxies) else 'doğrudan / proxy bypass'


class ProbeRedirect(_SecureRedirect):
    max_redirections = 5

    def __init__(self, report, proxies=None):
        self.report, self.proxies = report, proxies or {}

    def redirect_request(self, request, response, code, message, headers, newurl):
        check_cancelled()
        self.report(f'HTTPS yönlendirmesi: hedef sunucu {host_label(newurl)}; HTTP {code}; bağlantı: {_route_label(newurl, self.proxies)}.')
        redirected = super().redirect_request(request, response, code, message, headers, newurl)
        # Each hop's proxy handler supplies its own credentials. In particular,
        # proxy authorization must never survive a redirect to a NO_PROXY host.
        for header in (*redirected.headers, *redirected.unredirected_hdrs):
            if header.casefold() in {'authorization', 'proxy-authorization', 'cookie'}:
                redirected.remove_header(header)
        return redirected

    def http_error_302(self, request, response, code, message, headers):
        try:
            check_cancelled()
            trace = getattr(request, '_source_trace', None)
            if trace is None:
                trace = {'url': request.full_url, 'hops': 0, 'deadline': time.monotonic() + TRANSFER_TIMEOUT}
            if trace['hops'] >= self.max_redirections:
                raise ProbeFailure('source_redirect_limit', 'HTTPS yönlendirmesi beş adım sınırını aştı; döngüyü veya depo yönlendirmesini kontrol edin.')
            remaining = trace['deadline'] - time.monotonic()
            if remaining <= 0:
                raise ProbeFailure('source_timeout', 'HTTPS yönlendirmesi aktarım süre bütçesinde tamamlanamadı; depo/proxy erişimini kontrol edin.')
            target = headers.get('location') or headers.get('uri')
            if not isinstance(target, str) or not target:
                raise ProbeFailure('source_url_invalid', 'Sunucunun HTTPS yönlendirme adresi eksik veya geçersiz.')
            target = checked_url(urljoin(request.full_url, target))
            redirected = self.redirect_request(request, response, code, message, headers, target)
            trace.update(url=target, hops=trace['hops'] + 1)
            redirected._source_trace = trace
        finally:
            # urllib's default handler drains fp.read() without a limit. All
            # requests here use Connection: close; discard redirect bodies.
            response.close()
        return self.parent.open(redirected, timeout=min(REQUEST_TIMEOUT, remaining))

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


@dataclass(frozen=True)
class Transfer:
    url: str
    size: int
    digests: dict[str, str]
    body: bytes | None = None
    content_type: str = ''


def verify_digest(transfer, expected):
    for algorithm in ('sha512', 'sha256'):
        if expected.get(algorithm):
            if any(hmac.compare_digest(transfer.digests[algorithm], digest) for digest in expected[algorithm]):
                return algorithm
            raise ProbeFailure('source_integrity_failed', 'İndirilen dosyanın hash değeri beklenen değerle uyuşmuyor; dosya kullanılmadı.')
    raise ProbeFailure('source_hash_missing', 'Dosya tamamen indirildi ancak beklenen SHA-256/SHA-512 değeri yok; bütünlük doğrulanamadı. Depo metadata/hash bilgisini kontrol edin.')


class ProbeClient:
    def __init__(self, opener, proxies, report):
        self.opener, self.proxies, self.report = opener, proxies, report

    def metadata(self, url, *, accept):
        return self._transfer(url, limit=METADATA_LIMIT, accept=accept, download=False)

    def download(self, url, *, limit=PACKAGE_LIMIT):
        return self._transfer(url, limit=limit, accept='application/octet-stream', download=True)

    def _transfer(self, url, *, limit, accept, download):
        check_cancelled()
        checked_url(url)
        route = _route_label(url, self.proxies)
        self.report(f'Sunucu: {host_label(url)}; HTTPS; bağlantı: {route}.')
        request = Request(url, headers={'Accept': accept, 'Accept-Encoding': 'identity',
                                        'User-Agent': 'AWCenter-Source-Check/1'})
        deadline = time.monotonic() + TRANSFER_TIMEOUT
        trace = {'url': url, 'hops': 0, 'deadline': deadline}
        request._source_trace = trace
        try:
            with self.opener.open(request, timeout=REQUEST_TIMEOUT) as response, _storage_cleanup() as cleanup:
                if response.status != 200:
                    raise http_failure(response.status)
                final_url = checked_url(response.geturl())
                if download:
                    try:
                        directory = cleanup.enter_context(tempfile.TemporaryDirectory(prefix='awcenter-source-check-'))
                        output = cleanup.enter_context((Path(directory) / 'download.bin').open('wb'))
                    except OSError as error:
                        raise _storage_failure(error) from None
                else:
                    output = io.BytesIO()
                size, digests = self._read(response, output, limit, deadline)
                return Transfer(final_url, size, digests, None if download else output.getvalue(),
                                response.headers.get('Content-Type', '').split(';', 1)[0].lower())
        except (OperationCancelled, ProbeFailure):
            raise
        except HTTPError as error:
            try:
                raise http_failure(error.code) from None
            finally:
                error.close()
        except (IncompleteRead, HTTPException):
            raise ProbeFailure('source_incomplete_download', 'Veri aktarımı tamamlanmadan bağlantı kesildi; dosya eksik. Proxy ve dosya sunucusunu kontrol edin.') from None
        except (URLError, OSError) as error:
            raise connection_failure(error, using_proxy=_using_proxy(trace['url'], self.proxies)) from None

    def _read(self, response, output, limit, deadline):
        declared = response.headers.get('Content-Length', '')
        if declared and (not re.fullmatch(r'[0-9]{1,20}', declared) or int(declared) > limit):
            raise ProbeFailure('source_size_limit', 'Yanıt boyutu denetim sınırını aşıyor veya boyut bilgisi geçersiz; aktarım durduruldu.')
        expected_size = int(declared) if declared else None
        hashes = {algorithm: hashlib.new(algorithm) for algorithm in ('sha256', 'sha512')}
        size, announced = 0, 0
        while True:
            check_cancelled()
            if time.monotonic() >= deadline:
                raise ProbeFailure('source_timeout', 'Veri aktarımı toplam süre sınırında tamamlanamadı; ağ ve dosya sunucusunu kontrol edin.')
            chunk = response.read1(64 * 1024)
            check_cancelled()
            if time.monotonic() >= deadline:
                raise ProbeFailure('source_timeout', 'Veri aktarımı toplam süre sınırında tamamlanamadı; ağ ve dosya sunucusunu kontrol edin.')
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise ProbeFailure('source_size_limit', 'Yanıt boyutu denetim sınırını aştı; aktarım durduruldu.')
            try:
                output.write(chunk)
            except OSError as error:
                raise _storage_failure(error) from None
            for digest in hashes.values():
                digest.update(chunk)
            if size - announced >= max(1024 * 1024, limit // 20):
                announced = size
                self.report(f'Aktarılan veri: {size // 1024} KiB.')
        if not size or (expected_size is not None and size != expected_size):
            raise ProbeFailure('source_incomplete_download', 'Yanıt boş veya indirme eksik; alınan boyut beklenen dosya boyutuyla uyuşmuyor. Dosya sunucusu ve proxy erişimini kontrol edin.')
        self.report(f'Veri aktarımı tamamlandı: {size} bayt.')
        return size, {algorithm: digest.hexdigest() for algorithm, digest in hashes.items()}
