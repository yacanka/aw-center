"""Process-scoped package trust: native defaults, tool roots and additive CA files."""

from contextlib import contextmanager
from pathlib import Path
import ssl
import subprocess
import tempfile

from .model import LauncherError
from .process import controlled_run, environment


def _tool_roots(command, tool_env):
    """Read local runtime trust anchors; never forward tool diagnostics or PEMs."""
    try:
        result = controlled_run(command, env=environment({**tool_env, 'NODE_OPTIONS': ''}),
                                capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise LauncherError('Paket TLS güven deposu hazırlanamadı; Python/Node kurulumunu kontrol edin.') from None
    if result.returncode or not result.stdout or len(result.stdout) > 4 * 1024 * 1024:
        raise LauncherError('Paket TLS güven deposu hazırlanamadı; Python/Node kurulumunu kontrol edin.')
    return result.stdout


def _python_roots(python, tool_env):
    code = ('import ssl; from pip._vendor import certifi; '
            'context = ssl.create_default_context(); '
            'context.load_verify_locations(cafile=certifi.where()); '
            'print("".join(ssl.DER_cert_to_PEM_cert(cert) '
            'for cert in context.get_ca_certs(binary_form=True)))')
    return _tool_roots([str(python), '-I', '-c', code], tool_env)


def _node_roots(node, tool_env):
    code = 'require("node:fs").writeFileSync(1, require("node:tls").rootCertificates.join("\\n"))'
    return _tool_roots([str(node), '-e', code], tool_env)


@contextmanager
def package_trust_environment(tool_env: dict, *, ca_file: Path | None = None,
                              python: str | Path | None = None,
                              node: str | Path | None = None):
    """Yield temporary trust overrides; certificate files are never distributable.

    Windows CA/ROOT stores are loaded by the native default context. Tool roots
    preserve public trust even when pip/npm are given an explicit bundle. Node
    extras are also kept for lifecycle scripts that make their own TLS requests.
    """
    values = environment(tool_env)
    extra_files = [ca_file] if ca_file else []
    if not ca_file:
        ambient = next((values.get(key) for key in ('PIP_CERT', 'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE')
                        if values.get(key)), None)
        if ambient:
            extra_files.append(Path(ambient))
    if values.get('NODE_EXTRA_CA_CERTS'):
        extra_files.append(Path(values['NODE_EXTRA_CA_CERTS']))
    try:
        context = ssl.create_default_context()
        for selected in extra_files:
            context.load_verify_locations(cafile=str(selected))
        if python:
            context.load_verify_locations(cadata=_python_roots(python, tool_env))
        if node:
            context.load_verify_locations(cadata=_node_roots(node, tool_env))
        roots = context.get_ca_certs(binary_form=True)
        if not roots:
            raise ValueError('No trusted CA certificates')
    except (OSError, ValueError):
        raise LauncherError('Paket CA güven deposu yüklenemedi; sistem sertifikalarını ve seçilen PEM CA dosyalarını kontrol edin.') from None
    # Do not reintroduce ambient NPM_CONFIG_CA/CAFILE after capture sanitizes them.
    clean = {key: value for key, value in tool_env.items()
             if key.upper() not in {'PIP_CERT', 'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE',
                                    'NPM_CONFIG_CA', 'NPM_CONFIG_CAFILE', 'NODE_EXTRA_CA_CERTS'}}
    with tempfile.TemporaryDirectory(prefix='awcenter-trust-') as temporary:
        bundle = Path(temporary) / 'trusted-ca.pem'
        bundle.write_text(''.join(ssl.DER_cert_to_PEM_cert(cert) for cert in roots), encoding='ascii')
        # Pip's Requests environment merge can override PIP_CERT/session.verify.
        clean.update(PIP_CERT=str(bundle), REQUESTS_CA_BUNDLE=str(bundle),
                     CURL_CA_BUNDLE=str(bundle), NODE_EXTRA_CA_CERTS=str(bundle),
                     NODE_TLS_REJECT_UNAUTHORIZED='1', NPM_CONFIG_STRICT_SSL='true')
        if node:
            clean['NPM_CONFIG_CAFILE'] = str(bundle)
        yield clean
