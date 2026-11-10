"""Resolve one exact locked sample without installing tools or executing packages."""
import base64
from dataclasses import dataclass, field
from html.parser import HTMLParser
import json
import re
from urllib.parse import parse_qs, unquote, urljoin, urlsplit, urlunsplit

from .source_probe import ProbeFailure, checked_url


@dataclass(frozen=True)
class Sample:
    name: str
    version: str
    expected: dict[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class PackageFile:
    url: str
    expected: dict[str, tuple[str, ...]]


def _invalid_metadata():
    return ProbeFailure('source_metadata_invalid', 'Geçerli paket metadata bilgisi alınamadı. Depo API adresini ve HTTP 200 dönen giriş/proxy sayfalarını kontrol edin.')


def _lock_text(path):
    try:
        if path is None or path.stat().st_size > 16 * 1024 * 1024:
            raise ValueError
        return path.read_text(encoding='utf-8')
    except (OSError, UnicodeError, ValueError):
        raise ProbeFailure('source_lock_invalid', 'Paket kilit dosyası okunamadı veya denetim sınırına uygun değil; kaynak paketini kontrol edin.') from None


def python_sample(project):
    for line in _lock_text(project.requirements).splitlines():
        match = re.fullmatch(r'([A-Za-z0-9][A-Za-z0-9_.-]{0,199})==([0-9][A-Za-z0-9.!+_-]{0,99})', line.strip())
        if match:
            return Sample(re.sub(r'[-_.]+', '-', match[1]).lower(), match[2])
    raise ProbeFailure('source_lock_invalid', 'Python kilidinde koşulsuz, tam sürümü sabitlenmiş örnek paket bulunamadı; kilit dosyasını kontrol edin.')


def _integrity(value):
    if not isinstance(value, str):
        raise _invalid_metadata()
    result = {}
    for item in value.split():
        algorithm, separator, encoded = item.partition('-')
        if algorithm not in {'sha256', 'sha512'}:
            continue
        try:
            digest = base64.b64decode(encoded.split('?', 1)[0], validate=True)
            if not separator or len(digest) != {'sha256': 32, 'sha512': 64}[algorithm]:
                raise ValueError
        except ValueError:
            raise _invalid_metadata() from None
        result.setdefault(algorithm, []).append(digest.hex())
    return {algorithm: tuple(values) for algorithm, values in result.items()}


def npm_sample(project):
    try:
        lock = json.loads(_lock_text(project.frontend / 'package-lock.json'))
        for key, value in lock['packages'].items():
            if not key.startswith('node_modules/') or not value.get('version'):
                continue
            name, version = key.removeprefix('node_modules/'), value['version']
            if (len(name) > 214 or not re.fullmatch(r'(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*', name)
                    or not isinstance(version, str) or not re.fullmatch(r'[0-9][A-Za-z0-9.!+_-]{0,99}', version)):
                raise ValueError
            return Sample(name, version, _integrity(value.get('integrity', '')))
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ProbeFailure('source_lock_invalid', 'npm kilit dosyasında geçerli, tam sürümü sabitlenmiş örnek paket bulunamadı; kaynak paketini kontrol edin.') from None
    raise ProbeFailure('source_lock_invalid', 'npm kilit dosyasında örnek paket bulunamadı.')


def _json_metadata(transfer):
    try:
        result = json.loads(transfer.body)
        if not isinstance(result, dict):
            raise ValueError
        return result
    except (ValueError, UnicodeError, TypeError):
        raise _invalid_metadata() from None


def _hashes(values):
    if not isinstance(values, dict):
        raise _invalid_metadata()
    result = {}
    for algorithm, length in (('sha256', 64), ('sha512', 128)):
        if algorithm in values:
            value = values[algorithm]
            if not isinstance(value, str) or not re.fullmatch(rf'[0-9a-fA-F]{{{length}}}', value):
                raise _invalid_metadata()
            result[algorithm] = (value.lower(),)
    return result


class _SimplePage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.files = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'a' and attributes.get('href'):
            url = attributes['href']
            parsed = urlsplit(url)
            filename = unquote(parsed.path.rsplit('/', 1)[-1])
            if filename.endswith(('.whl', '.tar.gz', '.zip')):
                fragments = parse_qs(parsed.fragment)
                hashes = {name: values[0] for name, values in fragments.items() if values}
                self.files.append({'filename': filename, 'url': urlunsplit(parsed._replace(fragment='')),
                                   'hashes': hashes})


def _python_files(transfer, sample):
    if transfer.content_type.endswith('json') or transfer.body.lstrip().startswith(b'{'):
        data = _json_metadata(transfer)
        if (not isinstance(data.get('files'), list) or
                re.sub(r'[-_.]+', '-', str(data.get('name', ''))).lower() != sample.name):
            raise _invalid_metadata()
        return data['files']
    try:
        page = _SimplePage()
        page.feed(transfer.body.decode('utf-8'))
    except (ValueError, UnicodeError):
        raise _invalid_metadata() from None
    if not page.files:
        raise _invalid_metadata()
    return page.files


def python_file(transfer, sample):
    for file in _python_files(transfer, sample):
        if not isinstance(file, dict) or not isinstance(file.get('filename'), str):
            raise _invalid_metadata()
        parts = file['filename'].removesuffix('.whl').split('-')
        if (not file['filename'].endswith('.whl') or len(parts) not in {5, 6}
                or re.sub(r'[-_.]+', '-', parts[0]).lower() != sample.name or parts[1] != sample.version
                or not {'py3', 'py311'}.intersection(parts[-3].split('.')) or parts[-2:] != ['none', 'any']):
            continue
        if not isinstance(file.get('url'), str):
            raise _invalid_metadata()
        url = checked_url(urljoin(transfer.url, file['url']))
        return PackageFile(url, _hashes(file.get('hashes', {})))
    raise ProbeFailure('source_version_missing', 'Kilitli örnek sürüm için platformdan bağımsız Python wheel dosyası bulunamadı. Depo kapsamını ve kilitli sürümü kontrol edin; başka sürüm indirilmedi.')


def npm_file(transfer, sample):
    data = _json_metadata(transfer)
    if data.get('name') != sample.name or not isinstance(data.get('versions'), dict):
        raise _invalid_metadata()
    version = data['versions'].get(sample.version)
    if version is None:
        raise ProbeFailure('source_version_missing', 'Kilitli npm örnek sürümü seçilen depoda bulunamadı; depo kapsamını ve sürüm erişimini kontrol edin.')
    if (not isinstance(version, dict) or version.get('name') != sample.name
            or version.get('version') != sample.version or not isinstance(version.get('dist'), dict)):
        raise _invalid_metadata()
    distribution = version['dist']
    url = checked_url(distribution.get('tarball'))
    expected = sample.expected or _integrity(distribution.get('integrity', ''))
    return PackageFile(url, expected)
