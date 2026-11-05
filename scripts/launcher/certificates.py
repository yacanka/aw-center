"""Process-scoped package trust: native defaults, tool roots and additive CA files."""

from contextlib import contextmanager, ExitStack
from pathlib import Path
import ssl
import subprocess
import tempfile

from .model import LauncherError
from .certificate_store import export_context
from .process import OperationCancelled, controlled_run, environment

_TRUST_STAGES = {
    'system': 'Sistem sertifikaları', 'extra_ca': 'Seçilen ek sertifikalar',
    'python': 'Python/pip sertifikaları', 'node': 'Node.js sertifikaları',
    'bundle': 'Birleşik sertifika dosyası', 'tool': 'Araç sertifikaları',
}


class PackageTrustError(LauncherError):
    """Expose the failed export step and reviewed types, never CA/path/output data."""

    def __init__(self, stage, *, error=None, returncode=None):
        stage = stage if stage in _TRUST_STAGES else 'tool'
        self.code = 'package_trust_' + stage
        kinds = (NotImplementedError, ssl.SSLError, PermissionError, FileNotFoundError,
                 subprocess.TimeoutExpired, UnicodeError, ValueError, TypeError,
                 AttributeError, OSError, RuntimeError, ImportError)
        diagnostic = next((kind.__name__ for kind in kinds if isinstance(error, kind)),
                          'Beklenmeyen hata' if error else 'Geçersiz veya boş sertifika çıktısı')
        message = f'{_TRUST_STAGES[stage]} hazırlanamadı. Tanı: {diagnostic}.'
        for label, value in (('Çıkış kodu', returncode), ('WinError', getattr(error, 'winerror', None)),
                             ('errno', getattr(error, 'errno', None))):
            if type(value) is int and value != 0:
                message += f' {label}: {value}.'
        self.remedy = ('Seçilen CA dosyasının geçerli PEM biçiminde ve okunabilir olduğunu kontrol edin. TLS doğrulamasını kapatmayın.'
                       if stage == 'extra_ca' else
                       'Rapordaki sertifika aşaması ve tanı kodunu paylaşın; mevcut ortamı veya kurum sertifikalarını silmeyin. Tamamlanan kurulum aşamaları korunur.')
        super().__init__(message)


@contextmanager
def _trust_step(stage, progress=None):
    if progress:
        progress(_TRUST_STAGES[stage] + ' hazırlanıyor')
    try:
        yield
    except (OperationCancelled, PackageTrustError):
        raise
    except Exception as error:
        raise PackageTrustError(stage, error=error) from None


def _tool_roots(command, tool_env, *, stage='tool'):
    """Read local runtime trust anchors; never forward tool diagnostics or PEMs."""
    with _trust_step(stage):
        result = controlled_run(command, env=environment({**tool_env, 'NODE_OPTIONS': ''}),
                                capture_output=True, timeout=30, check=False)
        if result.returncode or not result.stdout or len(result.stdout) > 4 * 1024 * 1024:
            raise PackageTrustError(stage, returncode=result.returncode)
        # PEM is ASCII. Unrelated stderr warnings can use a Windows code page;
        # decoding those must not break a valid certificate export.
        return result.stdout.decode('ascii')


def _python_roots(python, tool_env):
    code = ('import runpy,ssl,sys; from pip._vendor import certifi; '
            'context = runpy.run_path(sys.argv[1])["export_context"](); '
            'context.load_verify_locations(cafile=certifi.where()); '
            'print("".join(ssl.DER_cert_to_PEM_cert(cert) '
            'for cert in context.get_ca_certs(binary_form=True)))')
    # -I ignores PYTHONDONTWRITEBYTECODE; pin the read-only probe explicitly.
    helper = Path(__file__).with_name('certificate_store.py')
    return _tool_roots([str(python), '-I', '-B', '-c', code, str(helper)], tool_env, stage='python')


def _node_roots(node, tool_env):
    code = 'require("node:fs").writeFileSync(1, require("node:tls").rootCertificates.join("\\n"))'
    return _tool_roots([str(node), '-e', code], tool_env, stage='node')


@contextmanager
def package_trust_environment(tool_env: dict, *, ca_file: Path | None = None,
                              python: str | Path | None = None,
                              node: str | Path | None = None, progress=None):
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
    with _trust_step('system', progress):
        context = export_context()
    for selected in extra_files:
        with _trust_step('extra_ca', progress):
            context.load_verify_locations(cafile=str(selected))
    if python:
        with _trust_step('python', progress):
            context.load_verify_locations(cadata=_python_roots(python, tool_env))
    if node:
        with _trust_step('node', progress):
            context.load_verify_locations(cadata=_node_roots(node, tool_env))
    with _trust_step('bundle', progress):
        roots = context.get_ca_certs(binary_form=True)
        if not roots:
            raise ValueError('No trusted CA certificates')
    # Do not reintroduce ambient NPM_CONFIG_CA/CAFILE after capture sanitizes them.
    clean = {key: value for key, value in tool_env.items()
             if key.upper() not in {'PIP_CERT', 'REQUESTS_CA_BUNDLE', 'CURL_CA_BUNDLE',
                                    'NPM_CONFIG_CA', 'NPM_CONFIG_CAFILE', 'NODE_EXTRA_CA_CERTS'}}
    with ExitStack() as cleanup:
        with _trust_step('bundle'):
            temporary = cleanup.enter_context(tempfile.TemporaryDirectory(prefix='awcenter-trust-'))
            bundle = Path(temporary) / 'trusted-ca.pem'
            bundle.write_text(''.join(ssl.DER_cert_to_PEM_cert(cert) for cert in roots), encoding='ascii')
        # Pip's Requests environment merge can override PIP_CERT/session.verify.
        clean.update(PIP_CERT=str(bundle), REQUESTS_CA_BUNDLE=str(bundle),
                     CURL_CA_BUNDLE=str(bundle), NODE_EXTRA_CA_CERTS=str(bundle),
                     NODE_TLS_REJECT_UNAUTHORIZED='1', NPM_CONFIG_STRICT_SSL='true')
        if node:
            clean['NPM_CONFIG_CAFILE'] = str(bundle)
        yield clean
