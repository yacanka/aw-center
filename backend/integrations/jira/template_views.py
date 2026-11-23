"""Central JIRA document templates. Publication is independent of project roles."""

import io
import sqlite3
from collections.abc import Mapping
from functools import wraps

from django.db import OperationalError, ProgrammingError
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.decorators import api_view
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from awcenter.api_errors import error_response
from awcenter.file_security import WORD_DOCUMENT_POLICY, validate_request_upload
from .sessions import JiraSessionError
from .template_catalog import PUBLIC_FIELDS, inspect_template, jira_server_id, read_source, save_template
from .template_issue import read_template_issue
from .template_jobs import generate_template_job
from .template_models import JiraDocumentTemplate


PUBLISH = "integrations.manage_jira_document_templates"


class TemplateWrite(serializers.Serializer):
    name = serializers.CharField(max_length=160, required=False)
    issue = serializers.CharField(max_length=2048, required=False)
    mapping = serializers.JSONField(required=False)
    version = serializers.IntegerField(min_value=1, required=False)
    archived = serializers.BooleanField(required=False)


def require_publisher(user):
    if not user.has_perm(PUBLISH):
        raise PermissionDenied("Central document template publisher permission is required.")


def template_payload(template):
    return {key: getattr(template, key) for key in PUBLIC_FIELDS}


def catalog(user):
    query = JiraDocumentTemplate.objects.all()
    return query if user.has_perm(PUBLISH) else query.filter(archived=False)


def is_missing_template_table(error):
    cause = error.__cause__
    if isinstance(cause, sqlite3.OperationalError):
        return str(cause) == f"no such table: {JiraDocumentTemplate._meta.db_table}"
    return getattr(cause, "sqlstate", None) == "42P01"  # PostgreSQL undefined_table


def template_api(methods):
    def decorate(function):
        @wraps(function)
        def handle(request, **kwargs):
            try:
                return function(request, **kwargs)
            except JiraSessionError as error:
                return error_response(error.detail, error.code,
                                      response_status=error.response_status)
        return api_view(methods)(handle)
    return decorate


def validate_keys(request, allowed):
    if not isinstance(request.data, Mapping):
        raise ValidationError({"detail": "Provide a request object."})
    if set(request.data) - set(allowed) or request.query_params:
        raise ValidationError({"detail": "The request contains unsupported parameters."})


def write(request, current=None):
    require_publisher(request.user)
    allowed = {"name", "issue", "mapping", "file"}
    validate_keys(request, allowed | ({"archived", "version"} if current else set()))
    serializer = TemplateWrite(data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    inputs = serializer.validated_data
    if current and "version" not in inputs:
        raise ValidationError({"detail": "Supply the current template version."})
    if not current and not inputs.get("name"):
        raise ValidationError({"detail": "Enter a template name."})
    upload = None
    if not current or "file" in request.data:
        upload = validate_request_upload(request, "file", WORD_DOCUMENT_POLICY)
    saved = save_template(request.user, inputs, upload, current)
    return Response(template_payload(saved), status=200 if current else 201)


@template_api(["GET", "POST"])
def document_templates(request):
    if request.method == "POST":
        return write(request)
    query = catalog(request.user).values(*PUBLIC_FIELDS)
    try:
        templates = list(query)
    except (OperationalError, ProgrammingError) as error:
        if not is_missing_template_table(error):
            raise
        return error_response(
            "The template library is unavailable until the database is updated.",
            "JIRA_DOCUMENT_TEMPLATE_SCHEMA_UNAVAILABLE",
            response_status=503,
        )
    return Response({"templates": templates})


@template_api(["GET", "PATCH"])
def document_template(request, template_id):
    if request.method == "PATCH":
        require_publisher(request.user)
    template = get_object_or_404(catalog(request.user), pk=template_id)
    if request.method == "PATCH":
        return write(request, template)
    return Response(template_payload(template))


@template_api(["POST"])
def inspect_document_template(request):
    require_publisher(request.user)
    validate_keys(request, {"file"})
    data = validate_request_upload(request, "file", WORD_DOCUMENT_POLICY).read()
    return Response({"placeholders": inspect_template(data)})


@template_api(["GET"])
def document_template_source(request, template_id):
    require_publisher(request.user)
    template = get_object_or_404(JiraDocumentTemplate, pk=template_id)
    return FileResponse(io.BytesIO(read_source(template)), as_attachment=True,
                        filename=f"template-{template.id}.docx")


@template_api(["POST"])
def resolve_document_issue(request):
    validate_keys(request, {"issue"})
    reference = serializers.CharField(max_length=2048).run_validation(request.data.get("issue"))
    issue = read_template_issue(request.user, reference)
    matches = JiraDocumentTemplate.objects.filter(
        archived=False, server_id=jira_server_id(), project_id=issue["project_id"],
        issue_type_id=issue["issue_type_id"],
    )
    return Response({**issue, "templates": list(matches.values(*PUBLIC_FIELDS))})


@template_api(["POST"])
def document_generation_job(request):
    validate_keys(request, {"issue", "template_id", "version", "manual_values"})
    return generate_template_job(request)
