"""TLS validation executed with the project's installed cryptography dependency."""

import argparse
import ipaddress
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization

from .model import LauncherError


def validate_tls_identity(certificate_file: Path, private_key_file: Path, host: str) -> None:
    """Require a live certificate/key pair whose SAN contains the static IP."""

    try:
        certificate = x509.load_pem_x509_certificate(certificate_file.read_bytes())
        private_key = serialization.load_pem_private_key(
            private_key_file.read_bytes(), password=None
        )
        certificate_key = certificate.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        private_public_key = private_key.public_key().public_bytes(
            serialization.Encoding.DER,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        san = certificate.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value
    except (OSError, ValueError, TypeError, x509.ExtensionNotFound) as error:
        raise LauncherError("TLS certificate or private key is invalid") from error
    if certificate_key != private_public_key:
        raise LauncherError("TLS certificate does not match the private key")
    if ipaddress.ip_address(host) not in san.get_values_for_type(x509.IPAddress):
        raise LauncherError("TLS certificate SAN does not contain the production IPv4 address")
    now = datetime.now(timezone.utc)
    if (
        certificate.not_valid_before_utc > now
        or certificate.not_valid_after_utc <= now + timedelta(days=1)
    ):
        raise LauncherError("TLS certificate is not currently valid for production")


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate the production TLS identity.")
    parser.add_argument("certificate_file", type=Path)
    parser.add_argument("private_key_file", type=Path)
    parser.add_argument("host")
    arguments = parser.parse_args()
    try:
        validate_tls_identity(arguments.certificate_file, arguments.private_key_file, arguments.host)
    except LauncherError as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
