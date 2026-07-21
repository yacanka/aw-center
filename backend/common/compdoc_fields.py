"""Server-owned table schema for compliance documents."""

from django.utils.text import capfirst


COMPDOC_TABLE_SCHEMA_VERSION = 2
EXCLUDED_FIELD_NAMES = {"cover_page", "status_flow"}
TEXT_FIELD_TYPES = {"CharField", "TextField", "EmailField", "UUIDField"}
DATE_FIELD_TYPES = {"DateField", "DateTimeField"}
NUMBER_FIELD_TYPES = {
    "IntegerField",
    "BigIntegerField",
    "PositiveIntegerField",
    "PositiveBigIntegerField",
    "FloatField",
    "DecimalField",
}
DEFAULT_COLUMN_ORDER = (
    "panel",
    "ata",
    "name",
    "cover_page_no",
    "cover_page_issue",
    "tech_doc_no",
    "tech_doc_issue",
    "ubm_target_date",
    "ubm_delivery_date",
    "moc",
    "status",
)
OPTION_SOURCES = {"panel": "panels", "ata": "atas"}
MOC_CHOICES = tuple((str(value), str(value)) for value in range(10)) + (("M", "M"),)


def get_compdoc_field_metadata(model):
    """Return ordered frontend-safe metadata for queryable document fields."""

    fields = [
        build_field_metadata(field)
        for field in model._meta.fields
        if field.name not in EXCLUDED_FIELD_NAMES
    ]
    order = {key: index for index, key in enumerate(DEFAULT_COLUMN_ORDER)}
    return sorted(fields, key=lambda field: (order.get(field["key"], len(order)), field["key"]))


def build_field_metadata(field):
    """Build one frontend-safe field definition from a Django model field."""

    field_type = field.get_internal_type()
    filter_kind = get_filter_kind(field)
    return {
        "key": field.name,
        "label": get_field_label(field),
        "type": field_type,
        "width": get_default_width(field_type),
        "filter_kind": filter_kind,
        "sortable": is_sortable(field),
        "default_visible": field.name in DEFAULT_COLUMN_ORDER,
        "ellipsis": field_type in TEXT_FIELD_TYPES,
        "choices": get_field_choices(field),
        "option_source": OPTION_SOURCES.get(field.name),
    }


def get_filter_kind(field):
    """Return the supported filter UI/query contract for one model field."""

    if field.name in OPTION_SOURCES or get_field_choices(field):
        return "select"
    field_type = field.get_internal_type()
    if field_type in TEXT_FIELD_TYPES:
        return "text"
    if field_type in DATE_FIELD_TYPES:
        return "date"
    if field_type in NUMBER_FIELD_TYPES:
        return "number"
    if field_type == "BooleanField":
        return "boolean"
    return "none"


def is_sortable(field):
    """Return whether database ordering is meaningful for the field."""

    return not field.is_relation and field.get_internal_type() != "JSONField"


def get_field_choices(field):
    """Return serializable model choices, including virtual delayed status."""

    choices = MOC_CHOICES if field.name == "moc" else tuple(field.flatchoices or ())
    values = [{"value": value, "label": str(label)} for value, label in choices]
    if field.name == "status":
        values.insert(-1, {"value": "delayed", "label": "Delayed"})
    return values


def get_field_label(field):
    """Return a readable label without exposing internal model details."""

    labels = {"ata": "ATA", "moc": "MoC", "ubm_target_date": "UBM Target Date"}
    labels["ubm_delivery_date"] = "UBM Delivery Date"
    return labels.get(field.name, capfirst(str(field.verbose_name).replace("_", " ")))


def get_default_width(field_type):
    """Return a practical Naive UI pixel width for a Django field type."""

    if field_type in DATE_FIELD_TYPES:
        return 140
    if field_type in NUMBER_FIELD_TYPES or field_type == "BooleanField":
        return 110
    if field_type == "TextField":
        return 260
    return 160
