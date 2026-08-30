"""Bounded DXL builder for the Requirement PoC Linker."""

import re

from .escape import dxl_quote

MAX_MODULE_OBJECTS = 10_000
MAX_LINK_CANDIDATES = 50_000
MAX_LINK_KEY_LENGTH = 1_024

LINKER_TEMPLATE = r'''
bool awc_is_space(string character) {
    return character == " " || character == "\t" || character == "\r"
}

string awc_trim(string value) {
    int first = 0
    int last = length(value) - 1
    while (first <= last && awc_is_space(value[first:first])) first++
    while (last >= first && awc_is_space(value[last:last])) last--
    if (first > last) return ""
    return value[first:last]
}

string awc_slice(string value, int start_index, int text_length) {
    int value_length = length(value)
    if (start_index >= value_length || text_length == 0) return ""
    if (text_length < 0 || start_index + text_length >= value_length) return value[start_index:]
    return value[start_index:start_index + text_length - 1]
}

bool awc_link_exists(Object source_object, string link_module_name, Object expected_target) {
    Link existing_link
    Object existing_target
    for existing_link in source_object -> link_module_name do {
        existing_target = target(existing_link)
        if (!null existing_target && existing_target == expected_target) return true
    }
    return false
}

string awc_ref_module_name = __REF_MODULE__
string awc_target_module_name = __TARGET_MODULE__
string awc_link_module_name = __LINK_MODULE__
string awc_ref_poc_attr = __REF_POC_ATTR__
string awc_ref_req_attr = __REF_REQ_ATTR__
string awc_target_poc_attr = __TARGET_POC_ATTR__
int awc_start_index = __START_INDEX__
int awc_text_length = __TEXT_LENGTH__

noError
Module awc_ref_module = __REF_OPEN__(awc_ref_module_name, false, true)
string awc_ref_open_error = lastError
if (!null awc_ref_open_error || null awc_ref_module) {
    awc_error("OPEN_REFERENCE_MODULE", awc_ref_open_error)
} else {
    noError
    Module awc_target_module = __TARGET_OPEN__(awc_target_module_name, false, true)
    string awc_target_open_error = lastError
    if (!null awc_target_open_error || null awc_target_module) {
        awc_error("OPEN_TARGET_MODULE", awc_target_open_error)
        close(awc_ref_module, false)
    } else {
        bool awc_has_error = false
        AttrDef awc_ref_poc_def = find(awc_ref_module, awc_ref_poc_attr)
        AttrDef awc_ref_req_def = find(awc_ref_module, awc_ref_req_attr)
        AttrDef awc_target_poc_def = find(awc_target_module, awc_target_poc_attr)
        if (null awc_ref_poc_def || !awc_ref_poc_def.object ||
            null awc_ref_req_def || !awc_ref_req_def.object ||
            null awc_target_poc_def || !awc_target_poc_def.object) {
            awc_error("ATTRIBUTE_NOT_FOUND", "A configured object attribute was not found")
            awc_has_error = true
        }

        Skip awc_groups = createString
        int awc_reference_count = 0
        int awc_candidate_count = 0
        if (!awc_has_error) {
            Object awc_ref_object
            for awc_ref_object in awc_ref_module do {
                if (awc_reference_count >= __MAX_OBJECTS__) {
                    awc_error("REFERENCE_OBJECT_LIMIT", "Reference module exceeds the object limit")
                    awc_has_error = true
                    break
                }
                awc_reference_count++
                string awc_docs = awc_ref_object.awc_ref_poc_attr ""
                string awc_requirement = awc_ref_object.awc_ref_req_attr ""
                int awc_cursor = 0
                int awc_docs_length = length(awc_docs)
                while (awc_cursor < awc_docs_length) {
                    string awc_remaining = awc_docs[awc_cursor:]
                    int awc_line_offset = 0
                    int awc_match_length = 0
                    bool awc_has_newline = findPlainText(
                        awc_remaining, "\n", awc_line_offset, awc_match_length, true
                    )
                    string awc_line
                    if (awc_has_newline) {
                        if (awc_line_offset == 0) awc_line = ""
                        else awc_line = awc_remaining[0:awc_line_offset - 1]
                        awc_cursor += awc_line_offset + awc_match_length
                    } else {
                        awc_line = awc_remaining
                        awc_cursor = awc_docs_length
                    }
                    string awc_key = awc_slice(
                        awc_trim(awc_line), awc_start_index, awc_text_length
                    )
                    if (length(awc_key) > __MAX_KEY_LENGTH__) {
                        awc_error("LINK_KEY_LIMIT", "A derived PoC key exceeds the length limit")
                        awc_has_error = true
                        break
                    }
                    Skip awc_requirements
                    if (!find(awc_groups, awc_key, awc_requirements)) {
                        awc_requirements = createString
                        put(awc_groups, awc_key, awc_requirements)
                    }
                    if (put(awc_requirements, awc_requirement, awc_ref_object)) {
                        awc_candidate_count++
                        if (awc_candidate_count > __MAX_CANDIDATES__) {
                            awc_error("LINK_CANDIDATE_LIMIT", "Link candidates exceed the limit")
                            awc_has_error = true
                            break
                        }
                    }
                }
                if (awc_has_error) break
            }
        }

        Skip awc_targets = createString
        int awc_target_count = 0
        if (!awc_has_error) {
            Object awc_target_object
            for awc_target_object in awc_target_module do {
                if (awc_target_count >= __MAX_OBJECTS__) {
                    awc_error("TARGET_OBJECT_LIMIT", "Target module exceeds the object limit")
                    awc_has_error = true
                    break
                }
                awc_target_count++
                string awc_target_key = awc_target_object.awc_target_poc_attr ""
                put(awc_targets, awc_target_key, awc_target_object)
            }
        }

        int awc_group_count = 0
        int awc_match_count = 0
        int awc_missing_count = 0
        int awc_created_count = 0
        int awc_existing_count = 0
        if (!awc_has_error) {
            Skip awc_group_requirements
            for awc_group_requirements in awc_groups do {
                string awc_group_key = (string key awc_groups)
                awc_group_count++
                Object awc_group_object
                for awc_group_object in awc_group_requirements do {
                    string awc_group_requirement = (string key awc_group_requirements)
                    awc_emit("GROUP\t" awc_escape(awc_group_key) "\t" awc_escape(awc_group_requirement))
                }
                Object awc_matched_target
                if (!find(awc_targets, awc_group_key, awc_matched_target)) {
                    awc_emit("MISSING\t" awc_escape(awc_group_key))
                    awc_missing_count++
                    continue
                }
                awc_emit("TARGET\t" awc_escape(awc_group_key))
                awc_match_count++
                if (__ACTIVE__) {
                    for awc_group_object in awc_group_requirements do {
                        Object awc_link_source = __LINK_SOURCE__
                        Object awc_link_target = __LINK_TARGET__
                        noError
                        bool awc_already_linked = awc_link_exists(
                            awc_link_source, awc_link_module_name, awc_link_target
                        )
                        string awc_lookup_error = lastError
                        if (!null awc_lookup_error) {
                            awc_error("CHECK_EXISTING_LINK", awc_lookup_error)
                            awc_has_error = true
                            break
                        }
                        if (awc_already_linked) {
                            awc_existing_count++
                            continue
                        }
                        noError
                        awc_link_source -> awc_link_module_name -> awc_link_target
                        string awc_link_error = lastError
                        if (!null awc_link_error) {
                            awc_error("CREATE_LINK", awc_link_error)
                            awc_has_error = true
                            break
                        }
                        awc_created_count++
                    }
                }
                if (awc_has_error) break
            }
        }

        if (!awc_has_error && __ACTIVE__) {
            noError
            save(__SOURCE_MODULE__)
            string awc_save_error = lastError
            if (!null awc_save_error) {
                awc_error("SAVE_SOURCE_MODULE", awc_save_error)
                awc_has_error = true
            }
        }
        if (!awc_has_error) {
            awc_emit(
                "SUMMARY\t" (awc_reference_count "") "\t" (awc_group_count "") "\t"
                (awc_candidate_count "") "\t" (awc_match_count "") "\t"
                (awc_missing_count "") "\t" (awc_created_count "") "\t"
                (awc_existing_count "")
            )
            awc_ok("REQUIREMENT_LINKER_DONE")
        }

        Skip awc_cleanup
        for awc_cleanup in awc_groups do delete(awc_cleanup)
        delete(awc_groups)
        delete(awc_targets)
        close(awc_target_module, false)
        close(awc_ref_module, false)
    }
}
'''.strip()


def link_requirements(
    ref_module_name: str,
    target_module_name: str,
    link_module_name: str,
    ref_attr_poc: str,
    ref_attr_req: str,
    target_attr_poc: str,
    start_index: int,
    text_length: int,
    direction: str,
    activeness: bool,
) -> str:
    """Build the fixed-purpose PoC grouping and linking operation."""

    if direction not in {"ref2tar", "tar2ref"}:
        raise ValueError("Unsupported link direction.")
    if int(start_index) < 0 or int(text_length) < -1:
        raise ValueError("Unsupported text slice.")
    active = bool(activeness)
    replacements = {
        "__REF_MODULE__": dxl_quote(ref_module_name),
        "__TARGET_MODULE__": dxl_quote(target_module_name),
        "__LINK_MODULE__": dxl_quote(link_module_name),
        "__REF_POC_ATTR__": dxl_quote(ref_attr_poc),
        "__REF_REQ_ATTR__": dxl_quote(ref_attr_req),
        "__TARGET_POC_ATTR__": dxl_quote(target_attr_poc),
        "__START_INDEX__": str(int(start_index)),
        "__TEXT_LENGTH__": str(int(text_length)),
        "__MAX_OBJECTS__": str(MAX_MODULE_OBJECTS),
        "__MAX_CANDIDATES__": str(MAX_LINK_CANDIDATES),
        "__MAX_KEY_LENGTH__": str(MAX_LINK_KEY_LENGTH),
        "__ACTIVE__": "true" if active else "false",
        "__REF_OPEN__": "edit" if active and direction == "ref2tar" else "read",
        "__TARGET_OPEN__": "edit" if active and direction == "tar2ref" else "read",
        "__LINK_SOURCE__": "awc_group_object" if direction == "ref2tar" else "awc_matched_target",
        "__LINK_TARGET__": "awc_matched_target" if direction == "ref2tar" else "awc_group_object",
        "__SOURCE_MODULE__": "awc_ref_module" if direction == "ref2tar" else "awc_target_module",
    }
    markers = re.compile("|".join(re.escape(marker) for marker in replacements))
    return markers.sub(lambda match: replacements[match.group(0)], LINKER_TEMPLATE)
