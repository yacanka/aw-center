"""Reviewed pip failure evidence; never publish raw subprocess diagnostics."""
from pathlib import Path
import re

_NAME = r'[A-Za-z0-9][A-Za-z0-9._-]{0,199}'
# Deliberately conservative: unfamiliar/local version forms simply omit the pin.
_VERSION = r'[0-9]+(?:\.[0-9]+)*(?:(?:a|b|rc|\.post|\.dev)[0-9]+)*(?:\+(?:cpu|cu[0-9]+))?'
_PIN = re.compile(rf'({_NAME})(?:\[[A-Za-z0-9_,.-]+\])?==({_VERSION})(?:\s*;[^\r\n]*)?')

# Fixed labels and remedies only. Transport/TLS diagnostics are handled by the
# caller first; these categories must not change source fallback authorization.
_FAILURES = (
    ((r"^ERROR: Package .+ requires a different Python:",),
     'package_python_incompatible',
     'Paket kullanılan Python sürümüyle uyumsuz (requires a different Python).',
     'Manager için desteklenen CPython 3.11 x64 ortamını ve kilitli paketin Python sürüm koşulunu kontrol edin.'),
    ((r'^ERROR: ResolutionImpossible\b', r'^ERROR: Cannot install .+ because these package versions have conflicting dependencies\.',
      rf'^{_NAME} \S+ has requirement .+, but you have .+\.$'),
     'package_dependency_conflict',
     'Paket sürümleri arasında bağımlılık uyuşmazlığı var (ResolutionImpossible / dependency conflict).',
     'Kilitli sürümleri ve kurulu ortamı birlikte kontrol edin; paketleri tek tek silmeyin veya rastgele sürüm değiştirmeyin.'),
    ((rf'^{_NAME} \S+ requires .+, which is not installed\.$',),
     'package_dependency_missing',
     'Kurulu paketin gerekli bir bağımlılığı eksik (pip check: dependency not installed).',
     'Kilitli bağımlılıkların tamamının aynı Python ortamına kurulabildiğini doğrulayın; Manager kurulumunu yeniden çalıştırın.'),
    ((r'^ERROR: Failed building wheel for ', r'^Failed to build '),
     'package_wheel_build_failed',
     'Paketin wheel dosyası derlenemedi (Failed building wheel).',
     'Kilitli sürüm için CPython 3.11/Windows x64 uyumlu wheel dosyasının izinli depoda bulunduğunu kontrol edin; kaynak derlemesi gerekiyorsa derleme bağımlılıklarını doğrulayın.'),
    ((r'^error: metadata-generation-failed\b',),
     'package_metadata_failed',
     'Paket metadatası oluşturulamadı (metadata-generation-failed).',
     'Kilitli paketin wheel dosyasını, Python uyumluluğunu ve gerekiyorsa kaynak derleme bağımlılıklarını kontrol edin.'),
    ((r'^error: subprocess-exited-with-error\b',),
     'package_build_subprocess_failed',
     'Paket hazırlama/derleme alt süreci hata verdi (subprocess-exited-with-error).',
     'Kilitli sürümün uyumlu wheel dosyasını ve derleme bağımlılıklarını kontrol edin; bu hata tek başına ağ sorunu olduğunu göstermez.'),
    ((r'^ERROR: No matching distribution found for ',
      r'^ERROR: Could not find a version that satisfies the requirement '),
     'package_distribution_not_found',
     'İstenen paket sürümü için uygun dağıtım bulunamadı (No matching distribution found).',
     'Kilitli sürümün seçilen depoda bulunduğunu ve Python 3.11/Windows x64 uyumluluğunu kontrol edin. Bu mesaj tek başına paketin tüm depolarda bulunmadığını kanıtlamaz.'),
)


def pip_failure(output: str) -> tuple[str, str, str] | None:
    """Recognize error families without copying any variable diagnostic text."""
    output = "\n".join(line.strip() for line in output.splitlines())
    for patterns, code, message, remedy in _FAILURES:
        if any(re.search(pattern, output, re.MULTILINE | re.IGNORECASE) for pattern in patterns):
            return code, message, remedy
    return None


def _normalize(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower()


def _locked_pins(requirements: Path | None) -> dict[str, str]:
    """Only a caller-selected lock may authorize package names in the report."""
    if requirements is None:
        return {}
    try:
        with Path(requirements).open(encoding='utf-8') as source:
            text = source.read(2 * 1024 * 1024 + 1)
    except (OSError, UnicodeError, ValueError):
        return {}
    if len(text) > 2 * 1024 * 1024:
        return {}
    result = {}
    for line in text.splitlines():
        match = _PIN.fullmatch(line.strip())
        if match and len(match[2]) <= 80:
            result.setdefault(_normalize(match[1]), f'{match[1]}=={match[2]}')
    return result


def locked_failure_packages(output: str, requirements: Path | None) -> tuple[str, ...]:
    """Attribute explicit error subjects, not the last progress/ignored package.

    Error strings are untrusted. Even syntactically valid package names can be
    secrets, so render only names AND versions taken from the selected lock.
    """
    pins = _locked_pins(requirements)
    found = []
    subject_patterns = (
        r'^ERROR: (?:No matching distribution found for|Could not find a version that satisfies the requirement) (.+)$',
        r"^ERROR: Package '([^']+)' requires a different Python:.*$",
        r'^ERROR: Failed building wheel for (.+)$',
        r'^Failed to build (.+)$',
        r'^ERROR: Cannot install (.+) because these package versions have conflicting dependencies\.$',
        rf'^({_NAME}) \S+ (?:requires|has requirement) (.+?)(?:, which is not installed\.|, but you have .+\.)$',
    )
    for line in output.splitlines():
        for pattern in subject_patterns:
            match = re.fullmatch(pattern, line.strip(), re.IGNORECASE)
            if not match:
                continue
            groups = match.groups()
            if line.strip().lower().startswith('failed to build '):
                groups = tuple(groups[0].split())
            for group in groups:
                # Match only requirement subjects at boundaries, not names in
                # URL/path/query substrings or arbitrary trailing prose.
                for name in re.findall(rf'(?:^|, | and )({_NAME})(?=$|[\[<>=!~ ,])', group):
                    pin = pins.get(_normalize(name))
                    if pin and pin not in found:
                        found.append(pin)
                        if len(found) == 5:
                            return tuple(found)
    return tuple(found)
