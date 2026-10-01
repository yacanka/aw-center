"""Deterministic server-only two-file packages for private job input."""

import hashlib
import json
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_STORED

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile

from awcenter.file_security import UploadPolicy, validate_uploaded_file
from automations.catalog import COMPARISON_PACKAGE_POLICY as PACKAGE_POLICY
from .contracts import CompareError, check_limit

INPUT_POLICY = UploadPolicy(frozenset({'.docx', '.docm', '.xlsx', '.xlsm', '.pdf'}))
# Internal only: never used to accept user-supplied ZIP uploads.
FAMILIES = {'.docx': 'word', '.docm': 'word', '.xlsx': 'excel', '.xlsm': 'excel', '.pdf': 'pdf'}


def file_family(name):
    family = FAMILIES.get(Path(name).suffix.lower())
    if family is None:
        raise CompareError('Select supported Word, Excel or PDF files.')
    return family


def create_package(first, second):
    family = file_family(first.name)
    if family != file_family(second.name):
        raise CompareError('Both files must be the same type: Word, Excel or PDF.', 'COMPARE_FORMAT_MISMATCH')
    output = BytesIO()
    manifest = {'version': 1, 'family': family, 'files': {}}
    with ZipFile(output, 'w', compression=ZIP_STORED) as archive:
        for key, upload in (('first', first), ('second', second)):
            upload.seek(0)
            content = upload.read()
            manifest['files'][key] = {'name': upload.name, 'sha256': hashlib.sha256(content).hexdigest()}
            archive.writestr(ZipInfo(key, date_time=(1980, 1, 1, 0, 0, 0)), content)
        archive.writestr(ZipInfo('manifest.json', date_time=(1980, 1, 1, 0, 0, 0)),
                         json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode())
    check_limit(output.tell() > PACKAGE_POLICY.maximum_bytes, 'The combined upload exceeds the comparison package limit.')
    return ContentFile(output.getvalue(), name='comparison.zip'), family


def read_package(path):
    with ZipFile(path) as archive:
        if sorted(archive.namelist()) != ['first', 'manifest.json', 'second']:
            raise CompareError('Stored comparison input is invalid.', 'COMPARE_INPUT_CORRUPT')
        for info in archive.infolist():
            limit = 4096 if info.filename == 'manifest.json' else INPUT_POLICY.maximum_bytes
            check_limit(info.file_size > limit, 'Stored comparison input exceeds the size limit.')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('version') != 1:
            raise CompareError('Stored comparison input version is unsupported.', 'COMPARE_INPUT_CORRUPT')
        contents = []
        for key in ('first', 'second'):
            content = archive.read(key)
            entry = manifest['files'][key]
            if hashlib.sha256(content).hexdigest() != entry['sha256'] or file_family(entry['name']) != manifest['family']:
                raise CompareError('Stored comparison input failed integrity verification.', 'COMPARE_INPUT_CORRUPT')
            validate_uploaded_file(SimpleUploadedFile(entry['name'], content, content_type='application/octet-stream'), INPUT_POLICY)
            contents.append(content)
    return manifest['family'], contents
