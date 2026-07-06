from django.utils.text import capfirst

FILTERABLE_FIELD_TYPES = {"CharField", "TextField", "EmailField", "IntegerField", "BigIntegerField", "PositiveIntegerField", "DateField", "DateTimeField", "BooleanField"}
TEXT_FIELD_TYPES = {"CharField", "TextField", "EmailField"}


def get_compdoc_field_metadata(model):
    """Return frontend-safe column metadata for concrete compliance-document fields."""

    return [build_field_metadata(field) for field in model._meta.fields]


def build_field_metadata(field):
    """Build one frontend-safe field metadata object from a Django model field."""

    field_type = field.get_internal_type()
    return {
        "key": field.name,
        "label": get_field_label(field),
        "type": field_type,
        "width": get_default_width(field_type),
        "filter": field_type in FILTERABLE_FIELD_TYPES,
        "sorter": True,
        "ellipsis": field_type in TEXT_FIELD_TYPES,
    }


def get_field_label(field):
    """Return a readable label without exposing internal model details."""

    return capfirst(str(field.verbose_name).replace("_", " "))


def get_default_width(field_type):
    """Return a practical n-data-table width hint for a Django field type."""

    if field_type in {"DateField", "DateTimeField"}:
        return 13
    if field_type in {"IntegerField", "BigIntegerField", "PositiveIntegerField"}:
        return 10
    return 15
