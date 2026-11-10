"""Safe generic query filtering for model-backed list endpoints."""

PAGINATION_QUERY_PARAMETERS = {"page", "page_size"}
TEXT_FIELD_TYPES = {"CharField", "TextField", "EmailField"}
BOOLEAN_FIELD_TYPES = {"BooleanField"}
TRUE_QUERY_VALUES = {"1", "true", "yes", "on"}
FALSE_QUERY_VALUES = {"0", "false", "no", "off"}


def get_query_values(request, name):
    """Return non-empty query values for DRF or Django requests."""

    query_parameters = getattr(request, "query_params", request.GET)
    values = query_parameters.getlist(name)
    return [value for value in values if value not in (None, "")]


def get_boolean_filter_value(value):
    """Return a bool for supported query values, otherwise ignore the filter."""

    normalized_value = str(value).strip().lower()
    if normalized_value in TRUE_QUERY_VALUES:
        return True
    if normalized_value in FALSE_QUERY_VALUES:
        return False
    return None


def get_filter_expression(field, values):
    """Build a safe lookup expression for a model field and values."""

    if not values:
        return None
    field_type = field.get_internal_type()
    if field_type in BOOLEAN_FIELD_TYPES:
        boolean_value = get_boolean_filter_value(values[0])
        return None if boolean_value is None else (field.name, boolean_value)
    if len(values) > 1:
        return f"{field.name}__in", values
    if field_type in TEXT_FIELD_TYPES:
        return f"{field.name}__icontains", values[0]
    return field.name, values[0]


def filtered_queryset(request, queryset):
    """Apply safe server-side filters for model-backed list querysets."""

    model = getattr(queryset, "model", None)
    if model is None:
        return queryset
    fields = {field.name: field for field in model._meta.fields}
    for name, field in fields.items():
        if name in PAGINATION_QUERY_PARAMETERS:
            continue
        expression = get_filter_expression(field, get_query_values(request, name))
        if expression:
            queryset = queryset.filter(**{expression[0]: expression[1]})
    return queryset
