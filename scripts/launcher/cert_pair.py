"""Generate a self-signed server leaf using the application's cryptography package."""

from datetime import datetime, timedelta, timezone
import ipaddress
import json
import sys


def generate(host):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    try:
        address = ipaddress.ip_address(host)
        name = x509.IPAddress(ipaddress.ip_address('127.0.0.1') if address.is_unspecified else address)
    except ValueError:
        name = x509.DNSName(host.encode('idna').decode('ascii'))
    key = ec.generate_private_key(ec.SECP256R1())
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'AW Center')])
    now = datetime.now(timezone.utc)
    certificate = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - timedelta(minutes=5)).not_valid_after(now + timedelta(days=365))
                   .add_extension(x509.SubjectAlternativeName([name]), critical=False)
                   .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
                   .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
                   .sign(key, hashes.SHA256()))
    return [certificate.public_bytes(serialization.Encoding.PEM).decode('ascii'),
            key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()).decode('ascii')]


if __name__ == '__main__':
    # Private pipe to the Manager worker only; never a user-facing log.
    print(json.dumps(generate(sys.argv[1])))
