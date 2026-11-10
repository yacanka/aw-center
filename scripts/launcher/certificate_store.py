"""Certificate export without replacing the process's HTTPS verification provider.

Some native TLS providers (notably truststore) deliberately do not implement
get_ca_certs(). Use CPython's OpenSSL context only for that local export, with
the same Windows CA/ROOT and SERVER_AUTH filtering as stdlib ssl. No connection
uses this fallback, and no SSL class is patched or third-party hook removed.
"""

import _ssl
import ssl
import sys
import warnings


def export_context():
    context = ssl.create_default_context()
    try:
        context.get_ca_certs(binary_form=True)
        return context
    except NotImplementedError:
        pass  # Native verification is supported; certificate export is not.
    context = _ssl._SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    if sys.platform == 'win32':
        for name in ('CA', 'ROOT'):
            _load_windows_roots(context, name)
    context.set_default_verify_paths()
    return context


def _load_windows_roots(context, name):
    certificates = bytearray()
    try:
        for certificate, encoding, trust in ssl.enum_certificates(name):
            if encoding == 'x509_asn' and (trust is True or ssl.Purpose.SERVER_AUTH.oid in trust):
                certificates.extend(certificate)
    except PermissionError:
        # Match stdlib's treatment of unavailable stores. The caller still
        # rejects an empty final store; explicit CA file failures are fatal.
        warnings.warn('unable to enumerate Windows certificate store')
    if certificates:
        context.load_verify_locations(cadata=certificates)
