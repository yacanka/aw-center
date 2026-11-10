"""JIRA display preference service; separate from user-created JIRA content."""

from users.preference_service import mutate_extra_settings
from .record_serializers import JIRA_PROJECT_SLUGS
from .watcher_fields import MAX_DETAIL_FIELDS, is_detail_field_id

def normalize_jira_preferences(extra_settings):
    raw = extra_settings.get("watcher", {}) if isinstance(extra_settings, dict) else {}
    raw = raw if isinstance(raw, dict) else {}
    selections = raw.get("detail_fields", {})
    components = raw.get("component_fields", {})
    return {
        "outstanding_only": raw.get("outstanding_only") is True,
        "detail_fields": {
            slug: list(dict.fromkeys(value)) for slug, value in selections.items()
            if slug in JIRA_PROJECT_SLUGS and isinstance(value, list)
            and len(value) <= MAX_DETAIL_FIELDS and all(is_detail_field_id(item) for item in value)
        } if isinstance(selections, dict) else {},
        "component_fields": {
            key: list(dict.fromkeys(value)) for key, value in components.items()
            if isinstance(key, str) and (key == "none" or (key.startswith("component:") and 10 < len(key) <= 265))
            and isinstance(value, list) and len(value) <= MAX_DETAIL_FIELDS
            and all(is_detail_field_id(item) for item in value)
        } if isinstance(components, dict) else {},
    }



def update_jira_preferences(user, values):
    def update(extra):
        watcher = normalize_jira_preferences(extra)
        if "outstanding_only" in values:
            watcher["outstanding_only"] = values["outstanding_only"]
        if "project_slug" in values:
            watcher["detail_fields"][values["project_slug"]] = list(dict.fromkeys(values["detail_field_ids"]))
        if "component_name" in values:
            name = values["component_name"]
            key = "none" if name is None else f"component:{name}"
            watcher["component_fields"][key] = list(dict.fromkeys(values["detail_field_ids"]))
        return {"extra_settings": {**extra, "watcher": watcher}}
    preferences = mutate_extra_settings(user, update)
    return normalize_jira_preferences(preferences.extra_settings)
