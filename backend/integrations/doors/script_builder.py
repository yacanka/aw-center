"""Build standalone DXL for validated Excel mappings; never execute DOORS writes."""

from .escape import dxl_quote


HELPERS = r'''
void awc_stop(string message) {
    print "ERROR: " message "\nChanges have not been saved automatically. Review the module before saving.\n"
    halt
}

void awc_warn(int excelRow, string message) {
    print "WARNING: Excel row " excelRow ": " message "\n"
}

void awc_require_attribute(Module source, string attributeName) {
    if (attributeName == "Object Number") return
    noError
    AttrDef definition = find(source, attributeName)
    string awc_definition_error = lastError
    if (!null awc_definition_error || null definition) {
        awc_stop("Attribute not found: " attributeName)
    }
    if (!definition.object) awc_stop("Not an object attribute: " attributeName)
}

bool awc_is_date(Module source, string attributeName) {
    if (attributeName == "Object Number") return false
    noError
    AttrDef definition = find(source, attributeName)
    AttrType attributeType = definition.type
    bool result = false
    if (!null attributeType) result = attributeType.type == attrDate
    string typeError = lastError
    if (!null typeError) awc_stop("Cannot read attribute type: " attributeName)
    return result
}

Date awc_parse_date(string canonical, string context) {
    if (canonical == "") awc_stop(context ": Invalid date; use dd.MM.yyyy or yyyy-MM-dd")
    noError
    Date parsed = date(canonical, "yyyy-MM-dd")
    string parseError = lastError
    if (!null parseError || null parsed) awc_stop(context ": Date conversion failed")
    if (stringOf(parsed, "yyyy-MM-dd") != canonical) awc_stop(context ": Invalid calendar date")
    return parsed
}

// Validate all date inputs before any row can modify the module.
void awc_validate_value(Module source, string attributeName, string value, string canonical, int excelRow) {
    if (value == "" || !awc_is_date(source, attributeName)) return
    string context = "Excel row " excelRow " attribute " attributeName
    Date parsed = awc_parse_date(canonical, context)
    noError
    AttrDef definition = find(source, attributeName)
    AttrType attributeType = definition.type
    bool hasMinimum = attributeType.minValue
    bool hasMaximum = attributeType.maxValue
    bool belowMinimum = false
    bool aboveMaximum = false
    if (hasMinimum) {
        Date minimum = attributeType.minValue
        belowMinimum = parsed < minimum
    }
    if (hasMaximum) {
        Date maximum = attributeType.maxValue
        aboveMaximum = parsed > maximum
    }
    string rangeError = lastError
    if (!null rangeError) awc_stop(context ": Cannot read date range")
    if (belowMinimum || aboveMaximum) awc_stop(context ": Date is outside the attribute's allowed range")
}

// Every read failure stops processing: it must never be treated as no match.
bool awc_attribute_matches(Object candidate, string attributeName, string expected, string canonical, bool contains) {
    string actual = ""
    if (attributeName == "Object Number") {
        noError
        bool readable = canRead(candidate)
        string accessError = lastError
        if (!null accessError || !readable) awc_stop("Cannot read Object Number")
        noError
        actual = number(candidate)
        string numberError = lastError
        if (!null numberError) awc_stop("Cannot read Object Number")
        int offset, length
        if (contains) return findPlainText(actual, expected, offset, length, true)
        return actual == expected
    }
    noError
    bool readable = canRead(candidate.attributeName)
    string awc_access_error = lastError
    if (!null awc_access_error || !readable) {
        awc_stop("Cannot read Unique Attribute: " attributeName)
    }
    noError
    actual = candidate.attributeName ""
    string awc_read_error = lastError
    if (!null awc_read_error) awc_stop("Cannot read Unique Attribute: " attributeName)
    if (awc_is_date(module(candidate), attributeName)) {
        if (actual != "") {
            noError
            Date actualDate = candidate.attributeName
            string dateError = lastError
            if (!null dateError || null actualDate) awc_stop("Cannot read date attribute: " attributeName)
            actual = stringOf(actualDate, "yyyy-MM-dd")
        }
        if (!contains || canonical != "") expected = canonical
    }
    int offset, length
    if (contains) return findPlainText(actual, expected, offset, length, true)
    return actual == expected
}

// Return false on a failed write so the caller can halt before another row.
bool SetObjectAttribute(Object target, string attributeName, string value, string canonical) {
    if (null target) {
        print "WARNING: Cannot write an attribute to a null object.\n"
        return false
    }
    noError
    AttrDef definition = find(module(target), attributeName)
    string awc_definition_error = lastError
    if (!null awc_definition_error || null definition) {
        print "WARNING: Attribute not found: " attributeName "\n"
        return false
    }
    if (!definition.object) {
        print "WARNING: Not an object attribute: " attributeName "\n"
        return false
    }
    noError
    bool writable = canWrite(target.attributeName)
    string awc_access_error = lastError
    if (!null awc_access_error || !writable) {
        print "WARNING: Cannot write attribute: " attributeName "\n"
        return false
    }
    bool isDate = awc_is_date(module(target), attributeName)
    Date parsed = null
    if (isDate && value != "") parsed = awc_parse_date(canonical, attributeName)
    noError
    if (isDate && value != "") target.attributeName = parsed
    else target.attributeName = value
    string awc_write_error = lastError
    if (!null awc_write_error) {
        print "WARNING: Attribute write failed: " attributeName "\n"
        return false
    }
    return true
}
'''.strip()

APPEND_HELPER = r'''
// Scan the entire hierarchy so filters and nested last objects cannot change placement.
Object awc_append_object(Module source) {
    Object awc_tail = null
    Object awc_candidate
    for awc_candidate in entire(source) do {
        if (isDeleted(awc_candidate)) continue
        if (level(awc_candidate) == 1) awc_tail = awc_candidate
    }
    noError
    Object o = null
    if (null awc_tail) o = create(source)
    else o = create after awc_tail
    string awc_create_error = lastError
    if (!null awc_create_error || null o) awc_stop("Object creation failed")
    return o
}
'''.strip()


def build_script(mappings, rows, excel_row_numbers, mode, date_rows):
    """Render composite matching and checked writes using the module's types."""

    if mode not in {"update", "create"}:
        raise ValueError("Unsupported script generation mode.")
    unique_indexes = [index for index, item in enumerate(mappings, 1) if item["search"]]
    conditions = "\n        && ".join(
        f"awc_attribute_matches(candidate, {dxl_quote(mappings[index - 1]['doors'])}, "
        f"awc_arr_{index}[row], awc_dates_{index}[row], "
        f"{'true' if mappings[index - 1].get('match_mode') == 'contains' else 'false'})"
        for index in unique_indexes
    )
    empty_keys = " || ".join(f'awc_arr_{index}[i] == ""' for index in unique_indexes)
    preflight = "\n".join(
        f"awc_require_attribute(refModule, {dxl_quote(item['doors'])})" for item in mappings
    )
    assignments = build_assignments(mappings, mode)
    operation = build_operation(assignments, mode)
    row_numbers = ",".join(str(number) for number in excel_row_numbers)
    append_helper = APPEND_HELPER if mode == "create" else ""
    validations = "\n".join(
        f"    awc_validate_value(refModule, {dxl_quote(item['doors'])}, "
        f"awc_arr_{index}[awc_row], awc_dates_{index}[awc_row], awc_excel_rows[awc_row])"
        for index, item in enumerate(mappings, 1)
        if not item["search"] or item.get("match_mode", "exact") == "exact" or mode == "create"
    )
    validation_empty_keys = empty_keys.replace("[i]", "[awc_row]")
    return f'''// Run in the current module opened for edit. Review and save changes manually.
{HELPERS}

Module refModule = current
if (null refModule) awc_stop("Module not found")
if (!isEdit(refModule)) awc_stop("Open the module for edit before running this script")
{preflight}

{build_arrays(mappings, rows, date_rows)}
int awc_excel_rows[] = {{{row_numbers}}}

int awc_row
for (awc_row = 0; awc_row < {len(rows)}; awc_row++) {{
    if ({validation_empty_keys}) continue
{validations}
}}

bool awc_matches(Object candidate, int row) {{
    return {conditions}
}}

{append_helper}

Object o
int i = 0
for (i = 0; i < {len(rows)}; i++) {{
    if ({empty_keys}) {{
        awc_warn(awc_excel_rows[i], "Empty Unique Attribute; row skipped")
        continue
    }}
{operation}
}}
print "Script completed. Changes have not been saved automatically. Review the module before saving.\\n"
'''


def build_arrays(mappings, rows, date_rows):
    """Keep workbook content in escaped literals with stable mapping indexes."""

    arrays = []
    for index in range(len(mappings)):
        values = ",".join(dxl_quote(row[index]) for row in rows)
        arrays.append(f"string awc_arr_{index + 1}[] = {{{values}}}")
        dates = ",".join(dxl_quote(row[index]) for row in date_rows)
        arrays.append(f"string awc_dates_{index + 1}[] = {{{dates}}}")
    return "\n".join(arrays)


def build_assignments(mappings, mode):
    """Keep update keys read-only; initialize every mapped field during creation."""

    assignments = []
    for index, item in enumerate(mappings, 1):
        if mode == "update" and item["search"]:
            continue
        assignments.append(
            f"        if (!SetObjectAttribute(o, {dxl_quote(item['doors'])}, "
            f"awc_arr_{index}[i], awc_dates_{index}[i])) {{\n"
            '            awc_warn(awc_excel_rows[i], "Attribute write failed")\n'
            '            awc_stop("Processing stopped; the object may be partially written")\n'
            "        }"
        )
    return "\n".join(assignments) or "        // No attribute updates were selected."


def build_operation(assignments, mode):
    """Search the live module for each row, including newly created objects."""

    if mode == "update":
        return f'''    bool awc_found = false
    for o in entire(refModule) do {{
        if (isDeleted(o)) continue
        if (!awc_matches(o, i)) continue
        awc_found = true
{assignments}
    }}
    if (!awc_found) awc_warn(awc_excel_rows[i], "Object not found; row skipped")'''
    return f'''    bool awc_found = false
    for o in entire(refModule) do {{
        if (isDeleted(o)) continue
        if (awc_matches(o, i)) {{
            awc_found = true
            break
        }}
    }}
    if (awc_found) {{
        awc_warn(awc_excel_rows[i], "Object already exists; row skipped")
        continue
    }}
    o = awc_append_object(refModule)
{assignments}'''
