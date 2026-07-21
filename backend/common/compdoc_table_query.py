"""Validated database queries for the compliance-document table."""

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from common.compdoc_fields import get_compdoc_field_metadata
from common.compdoc_workflow import parse_workflow_date


DATE_LOOKUPS = {"exact", "not", "gt", "gte", "lt", "lte"}
TRUE_VALUES = {"1", "true", "yes"}
FALSE_VALUES = {"0", "false", "no"}


def apply_compdoc_table_query(request, queryset):
    """Apply allow-listed filters and ordering from the server-owned field schema."""

    fields = {field["key"]: field for field in get_compdoc_field_metadata(queryset.model)}
    queryset = _apply_filters(request.query_params, queryset, fields)
    return _apply_ordering(request.query_params.get("ordering"), queryset, fields)


def _apply_filters(query, queryset, fields):
    for key, metadata in fields.items():
        if metadata["filter_kind"] == "date":
            queryset = _apply_date_filters(query, queryset, metadata)
            continue
        values = _query_values(query, key)
        if values:
            queryset = _apply_field_filter(queryset, metadata, values)
    return queryset


def _apply_field_filter(queryset, metadata, values):
    key = metadata["key"]
    kind = metadata["filter_kind"]
    if key == "status":
        return queryset.filter(_status_filter(values))
    if kind == "text":
        condition = Q()
        for value in values:
            condition |= Q(**{f"{key}__icontains": value})
        return queryset.filter(condition)
    if kind == "boolean":
        values = [_parse_boolean(key, value) for value in values]
    if kind == "number":
        values = [_parse_number(queryset.model, key, value) for value in values]
    return queryset.filter(**{f"{key}__in": values})


def _apply_date_filters(query, queryset, metadata):
    key = metadata["key"]
    field_lookup = f"{key}__date" if metadata["type"] == "DateTimeField" else key
    for lookup in DATE_LOOKUPS:
        parameter = key if lookup == "exact" else f"{key}__{lookup}"
        values = _query_values(query, parameter)
        if not values:
            continue
        parsed = _parse_date(key, values[-1])
        if lookup == "not":
            queryset = queryset.exclude(**{field_lookup: parsed})
        else:
            queryset = queryset.filter(**{f"{field_lookup}__{lookup}": parsed})
    return queryset


def _apply_ordering(value, queryset, fields):
    if not value:
        return queryset.order_by("-id")
    key = value.removeprefix("-")
    if key not in fields or not fields[key]["sortable"]:
        raise ValidationError({"ordering": f"Unsupported ordering field: {key}"})
    return queryset.order_by(value, "-id")


def _status_filter(values):
    requested = set(values)
    delayed = "delayed" in requested
    pending = "to_be_issued" in requested
    requested.discard("delayed")
    requested.discard("to_be_issued")
    condition = Q(status__in=requested) if requested else Q(pk__in=[])
    if delayed:
        condition |= Q(status="to_be_issued", ubm_target_date__lt=timezone.localdate())
    if pending:
        current_or_future = Q(ubm_target_date__gte=timezone.localdate()) | Q(
            ubm_target_date__isnull=True
        )
        condition |= Q(status="to_be_issued") & current_or_future
    return condition


def _query_values(query, key):
    return [value for value in query.getlist(key) if value not in (None, "")]


def _parse_date(key, value):
    parsed = parse_workflow_date(value)
    if parsed is None:
        raise ValidationError({key: "Use a valid ISO or DD.MM.YYYY date."})
    return parsed


def _parse_boolean(key, value):
    normalized = str(value).strip().lower()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False
    raise ValidationError({key: "Use true or false."})


def _parse_number(model, key, value):
    try:
        return model._meta.get_field(key).to_python(value)
    except (DjangoValidationError, TypeError, ValueError):
        raise ValidationError({key: "Use a valid number."}) from None
