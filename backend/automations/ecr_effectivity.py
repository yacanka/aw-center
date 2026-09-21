"""Suggest effectivity values during review without changing an approved plan."""

from integrations.jira.create_contract import public_field
from integrations.jira.effectivity import match_effectivity_options, split_effectivity_values

EFFECTIVITY_FIELD = "customfield_34115"


def add_effectivity_suggestion(result, metadata, raw_effectivity):
    """Offer only fully matched, bounded multiselect options for explicit acceptance."""

    field = next((item for item in metadata if item.get("id") == EFFECTIVITY_FIELD), None)
    if not field or not raw_effectivity:
        return result
    schema = field.get("schema") or {}
    if schema.get("type") != "array" or schema.get("items") != "option":
        return result
    exposed = public_field(field)
    exposed["required"] = bool(field.get("required"))
    options = exposed["allowedValues"]
    matches = split_effectivity_values(match_effectivity_options(
        str(raw_effectivity)[:2000], [item["label"] for item in options]
    ))
    values_by_label = {item["label"]: item["value"] for item in options}
    if not matches or any(label not in values_by_label for label in matches):
        return result
    if not any(item["id"] == EFFECTIVITY_FIELD for item in result["fields"]):
        result["fields"].append(exposed)
    result["effectivity_suggestion"] = {
        "values": [values_by_label[label] for label in matches],
        "labels": matches,
    }
    return result
