"""Authenticated, owner-scoped comparison entry points."""

from dataclasses import asdict
from datetime import timedelta
from functools import wraps
import json
from uuid import UUID

from django.conf import settings
from django.core.files import File
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from awcenter.api_errors import error_response
from awcenter.file_security import validate_request_upload
from awcenter.private_files import open_verified_private_file, PrivateFileIntegrityError
from jobs.api import job_creation_response
from jobs.models import Job, JobStatus
from jobs.services import create_job, require_idempotency_key

from .contracts import CompareError, PRESETS, resolve_options
from .packaging import INPUT_POLICY, create_package


def comparison_errors(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except CompareError as error:
            return error_response(error.detail, error.code, response_status=400)
        except (OSError, PrivateFileIntegrityError):
            return error_response('The stored comparison input is unavailable or failed integrity verification.',
                                  'COMPARE_ARTIFACT_UNAVAILABLE', response_status=409)
    return wrapped


def parameters(request):
    value = request.data.get('parameters', {})
    try:
        value = json.loads(value) if isinstance(value, str) else value
    except (ValueError, TypeError) as error:
        raise CompareError('Select valid comparison parameters.') from error
    if not isinstance(value, dict):
        raise CompareError('Select valid comparison parameters.')
    return value


def owned_inspection(request, identifier):
    try:
        identifier = UUID(str(identifier))
    except ValueError as error:
        raise CompareError('Select a valid inspection.') from error
    cutoff = timezone.now() - timedelta(days=settings.JOB_ARTIFACT_RETENTION_DAYS)
    return get_object_or_404(Job, pk=identifier, owner=request.user, kind='comparison.inspect',
                             status=JobStatus.SUCCEEDED, completed_at__gte=cutoff)


def inspection_data(job):
    with open_verified_private_file(job.output_file, job.output_sha256) as handle:
        return json.load(handle)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def presets(request):
    return Response({'presets': [{'id': key, **value} for key, value in PRESETS.items()], 'default': 'balanced'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
@comparison_errors
def inspection_detail(request, job_id):
    return Response(inspection_data(owned_inspection(request, job_id)))


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@comparison_errors
def create_inspection(request):
    return enqueue(request, inspection=True)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@comparison_errors
def create_comparison(request):
    return enqueue(request, inspection=False)


def enqueue(request, *, inspection):
    key = require_idempotency_key(request.headers.get('Idempotency-Key', ''))
    supplied = parameters(request)
    source_id = request.data.get('inspection_id')
    if source_id:
        source = owned_inspection(request, source_id)
        inspected = inspection_data(source)
        merged = {**inspected['options'], **supplied}
        options = resolve_options(merged, 'excel')
        selection = supplied.get('selection', inspected['selection']) if inspection else inspected['selection']
        if not inspection:
            validate_inspection_options(inspected, options, supplied)
        with open_verified_private_file(source.input_file, source.input_sha256) as handle:
            return persist(request, File(handle, name='comparison.zip'), 'excel', options, selection, inspection, key, source)
    first = validate_request_upload(request, 'first', INPUT_POLICY)
    second = validate_request_upload(request, 'second', INPUT_POLICY)
    package, family = create_package(first, second)
    if inspection and family != 'excel':
        raise CompareError('Inspection is only required for Excel workbooks.')
    if not inspection and family == 'excel':
        raise CompareError('Inspect the Excel tables before comparing them.', 'COMPARE_INSPECTION_REQUIRED')
    options = resolve_options(supplied, family)
    return persist(request, package, family, options, supplied.get('selection', {}), inspection, key)


def validate_inspection_options(inspected, options, supplied):
    if inspected['matching']['requires_input']:
        raise CompareError(inspected['matching']['reason'], 'COMPARE_MATCHING_REQUIRED')
    previous = inspected['options']
    changed_thresholds = any(getattr(options, name) != previous[name] for name in ('equal_ratio', 'weak_equal_ratio'))
    if changed_thresholds or 'selection' in supplied:
        raise CompareError('Inspect the tables again after changing matching settings.', 'COMPARE_INSPECTION_REQUIRED')


def persist(request, package, family, options, selection, inspection, key, source=None):
    validate_selection(selection)
    job, created = create_job(owner=request.user, kind='comparison.inspect' if inspection else 'comparison.compare',
        title='Inspect comparison tables' if inspection else 'Compare files',
        parameters={'family': family, 'options': asdict(options), 'selection': selection},
        uploaded_file=package, idempotency_key=key, request_id=getattr(request, 'request_id', ''), source_job=source)
    return job_creation_response(job, created)


def validate_selection(selection):
    if not isinstance(selection, dict):
        raise CompareError('Select valid table options.')
    # Bound JSON independently from the upload body and avoid persisting arbitrary
    # browser state. Detailed column validation happens against the parsed tables.
    if set(selection) - {'first', 'second', 'columns', 'matching'} or len(json.dumps(selection)) > 16000:
        raise CompareError('Select valid bounded table options.')
    for side in ('first', 'second'):
        table = selection.get(side, {})
        if not isinstance(table, dict) or set(table) - {'sheet', 'header_row'}:
            raise CompareError('Select valid table options.')
        if 'sheet' in table and (not isinstance(table['sheet'], str) or not 1 <= len(table['sheet']) <= 31):
            raise CompareError('Select a valid worksheet name.')
        if 'header_row' in table and (type(table['header_row']) is not int or not 1 <= table['header_row'] <= 20):
            raise CompareError('Select a header row from the first 20 rows.')
    matching = selection.get('matching', {})
    if not isinstance(matching, dict) or set(matching) - {'mode', 'keys'}:
        raise CompareError('Select valid row matching options.')
    if matching.get('mode', 'auto') not in ('auto', 'keys', 'position'):
        raise CompareError('Select a supported row matching method.')
    keys = matching.get('keys', [])
    if not isinstance(keys, list) or len(keys) > 3 or any(type(value) is not int or not 0 <= value < 100 for value in keys):
        raise CompareError('Select up to three identity columns.')
    columns = selection.get('columns', [])
    if not isinstance(columns, list) or len(columns) > 100:
        raise CompareError('Select valid column mappings.')
    for pair in columns:
        if not isinstance(pair, list) or len(pair) != 2 or any(type(value) is not int or not 0 <= value < 100 for value in pair):
            raise CompareError('Select valid column mappings.')
