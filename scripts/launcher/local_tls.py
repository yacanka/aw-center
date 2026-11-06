"""TLS trust limited to the explicitly configured, launcher-owned server.

Windows native TLS providers can discard non-CA leaves passed as a cafile.
Use CPython 3.11's OpenSSL context for this single pinned identity, without
changing the process SSL provider or trusting it for package downloads.
"""

import _ssl
import re
import ssl


class _LocalServerContext(_ssl._SSLContext):
    """Minimal stdlib socket adapter; certificate checks run before HTTP I/O."""

    @staticmethod
    def _encode_hostname(hostname):
        if hostname is None:
            return None
        return hostname.decode('ascii') if isinstance(hostname, bytes) else hostname.encode('idna').decode('ascii')

    def wrap_socket(self, sock, *, server_hostname=None):
        connection = ssl.SSLSocket._create(sock=sock, server_hostname=server_hostname, context=self)
        try:
            if connection.getpeercert(binary_form=True) != self.expected_certificate:
                raise ssl.SSLCertVerificationError('Server does not match the configured TLS identity')
        except BaseException:
            connection.close()
            raise
        return connection


def local_server_context(certificate: str):
    """Verify validity/IP and the exact first PEM leaf, including issued leaves.

    Partial-chain trust terminates at that explicit leaf. Exact DER matching also
    prevents a selected CA-capable server certificate authorizing another leaf.
    No ambient roots are loaded and no Windows certificate store is modified.
    """
    with open(certificate, 'rb') as source:
        content = source.read(1024 * 1024 + 1)
    match = re.search(rb'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', content, re.DOTALL)
    if len(content) > 1024 * 1024 or match is None:
        raise ssl.SSLError('Invalid configured TLS certificate')
    pem = match[0].decode('ascii')
    context = _LocalServerContext(ssl.PROTOCOL_TLS_CLIENT)
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
    context.load_verify_locations(cadata=pem)
    context.expected_certificate = ssl.PEM_cert_to_DER_cert(pem)
    return context
