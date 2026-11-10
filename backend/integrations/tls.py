"""Request-local additive TLS trust for outbound integration clients.

Windows CA/ROOT and OpenSSL defaults remain trusted alongside Requests' public
roots. An integration's explicit CA takes precedence over ambient bundle paths;
all selected bundles supplement these defaults rather than replacing them.
"""

from collections import OrderedDict
from contextlib import contextmanager
import os
import ssl
from threading import RLock

import requests
from requests.adapters import HTTPAdapter
from requests.exceptions import InvalidProxyURL, SSLError
from requests.utils import prepend_scheme_if_needed, select_proxy
from urllib3.util import parse_url


class SystemTrustAdapter(HTTPAdapter):
    """Keep isolated, bounded TLS contexts and the caller's HTTP retry policy."""

    def __init__(self, verification=True, **kwargs):
        self.verification = verification
        self._contexts = OrderedDict()
        self._trust_lock = RLock()
        super().__init__(**kwargs)

    def _verification(self, verify):
        return self.verification if self.verification is not True else verify

    def _context(self, verify, cert=None, *, proxy=False):
        with self._trust_lock:
            return self._cached_context(verify, cert, proxy=proxy)

    def _cached_context(self, verify, cert, *, proxy):
        identity = tuple(cert) if isinstance(cert, (tuple, list)) else cert
        key = (verify, identity, proxy)
        if key in self._contexts:
            self._contexts.move_to_end(key)
            return self._contexts[key]
        try:
            context = ssl.create_default_context()
            # Match Requests/urllib3: identity requires SAN, never legacy CN.
            context.hostname_checks_common_name = False
            context.load_verify_locations(cafile=requests.certs.where())
            if verify is not True:
                location = os.fspath(verify)
                selected = {'capath': location} if os.path.isdir(location) else {'cafile': location}
                context.load_verify_locations(**selected)
        except (OSError, ValueError, TypeError):
            raise SSLError('Integration TLS trust configuration is unavailable or invalid.') from None
        self._contexts[key] = context
        if len(self._contexts) > 2:
            self._contexts.popitem(last=False)
        return context

    def build_connection_pool_key_attributes(self, request, verify, cert=None):
        verify = self._verification(verify)
        host, pool = super().build_connection_pool_key_attributes(request, verify, cert)
        if verify is not False:
            pool['ssl_context'] = self._context(verify, cert)
            pool.pop('ca_certs', None)
            pool.pop('ca_cert_dir', None)
        return host, pool

    def get_connection_with_tls_context(self, request, verify, proxies=None, cert=None):
        """Use the same additive trust for HTTPS proxies and destination TLS."""
        host, pool = self.build_connection_pool_key_attributes(request, verify, cert)
        proxy = select_proxy(request.url, proxies)
        if not proxy:
            return self.poolmanager.connection_from_host(**host, pool_kwargs=pool)
        proxy = prepend_scheme_if_needed(proxy, 'http')
        parsed_proxy = parse_url(proxy)
        if not parsed_proxy.host:
            raise InvalidProxyURL('Proxy configuration is invalid.')
        options = {}
        if parsed_proxy.scheme == 'https' and 'ssl_context' in pool:
            # Target mTLS credentials must never enter the proxy's TLS context.
            options['proxy_ssl_context'] = self._context(self._verification(verify), proxy=True)
        manager = self.proxy_manager_for(proxy, **options)
        return manager.connection_from_host(**host, pool_kwargs=pool)

    def proxy_manager_for(self, proxy, **proxy_kwargs):
        # A changed ambient CA must not reuse another trust context's proxy pool.
        key = (proxy, proxy_kwargs.get('proxy_ssl_context'))
        with self._trust_lock:
            if key not in self.proxy_manager:
                manager = super().proxy_manager_for(proxy, **proxy_kwargs)
                self.proxy_manager.pop(proxy, None)
                self.proxy_manager[key] = manager
                if len(self.proxy_manager) > self._pool_connections:
                    self.proxy_manager.pop(next(iter(self.proxy_manager))).clear()
            return self.proxy_manager[key]

    def send(self, request, stream=False, timeout=None, verify=True, cert=None, proxies=None):
        return super().send(request, stream=stream, timeout=timeout,
                            verify=self._verification(verify), cert=cert, proxies=proxies)

    def cert_verify(self, conn, url, verify, cert):
        # The selected bundle is already validated in the isolated SSLContext.
        # Keep Requests' certificate/mTLS metadata without loading it a second time.
        try:
            super().cert_verify(conn, url, verify is not False, cert)
        except OSError:
            raise SSLError('Integration TLS certificate configuration is unavailable or invalid.') from None


def configure_session_tls(session, verification=True):
    """Configure real Requests transports; injected non-network fakes stay usable.

    Trust is a per-session snapshot. Configuration is lazy so malformed CAs fail at the transport
    boundary, before a connection sends credentials. Cookies, auth, proxies,
    headers and the existing adapter's retry settings are retained.
    """
    if not isinstance(session, requests.Session):
        return session
    previous = session.get_adapter('https://')
    adapter = SystemTrustAdapter(verification, max_retries=previous.max_retries,
                                 pool_connections=previous._pool_connections,
                                 pool_maxsize=previous._pool_maxsize,
                                 pool_block=previous._pool_block)
    session.mount('https://', adapter)
    previous.close()
    return session


@contextmanager
def tls_post(url, **kwargs):
    """Own the request-local session and streamed response through consumption."""
    with requests.Session() as session:
        configure_session_tls(session)
        with session.post(url, **kwargs) as response:
            yield response


def tls_head(url, *, verify=True, **kwargs):
    """Return an already-closed HEAD response; probes only inspect its status."""
    with requests.Session() as session:
        configure_session_tls(session, verify)
        response = session.head(url, verify=verify, **kwargs)
        response.close()
        return response
