"""Read-only DXL builders for the DOORS adapter."""

from collections.abc import Iterable

from .builder_common import open_module, attribute_fragments

CHECK_TEMPLATE = r'''
noError
{open_statement}
string awc_open_error = lastError
if (!null awc_open_error || null module) {{
    awc_error("OPEN_MODULE", awc_open_error)
}} else {{
    awc_ok("MODULE_OPENED")
    close(module, false)
}}
'''.strip()

LIST_TEMPLATE = r'''
noError
{open_statement}
string awc_open_error = lastError
if (!null awc_open_error || null module) {{
    awc_error("OPEN_MODULE", awc_open_error)
}} else {{
    {declarations}
    Object object
    int awc_count = 0
    for object in {iterable} do {{
        if (awc_count >= {limit}) break
        awc_emit("OBJECT\t" (object."Absolute Number" "") "\t" (awc_escape(identifier(object))"") "\t" (level(object) "") {fields})
        awc_count++
    }}
    close(module, false)
    awc_ok("LIST_OBJECTS_DONE")
}}
'''.strip()

GET_TEMPLATE = r'''
noError
{open_statement}
string awc_open_error = lastError
if (!null awc_open_error || null module) {{
    awc_error("OPEN_MODULE", awc_open_error)
}} else {{
    {declarations}
    Object object = object({absolute_number}, module)
    if (null object) {{
        awc_error("OBJECT_NOT_FOUND", "Object was not found")
    }} else {{
        awc_emit("OBJECT\t" (object."Absolute Number" "") "\t" (awc_escape(identifier(object))"") "\t" (level(object) "") {fields})
    }}
    close(module, false)
}}
'''.strip()

GET_ATTR = r'''
noError
{open_statement}
string awc_open_error = lastError
if (!null awc_open_error || null module) {{
    awc_error("OPEN_MODULE", awc_open_error)
}} else {{
    AttrDef object
	int offset, length
    bool isFound
	for object in module do {{
		isFound = findPlainText(object.name, "{search_text}", offset, length, {case_sensitive})
		if (isFound) {{
			break
		}}
	}}
    close(module, false)
	if (isFound) {{
        awc_emit("OBJECT\t" (object.name ""))
        awc_ok("OBJECT_FOUND")
    }} else {{
	    awc_error("OBJECT_NOT_FOUND", "Object was not found")
    }}
}}
'''

EXPORT_MODULE_TEMPLATE = r'''
noError
{open_statement}
string awc_open_error = lastError
if (!null awc_open_error || null module) {{
    awc_error("OPEN_MODULE", awc_open_error)
}} else {{
    AttrDef awc_attribute
    int awc_attribute_count = 0
    for awc_attribute in module do {{
        if (!awc_attribute.object) continue
        if (awc_attribute_count >= {attribute_limit}) {{
            awc_emit("ATTRIBUTES_TRUNCATED")
            break
        }}
        awc_emit("ATTRIBUTE\t" awc_escape(awc_attribute.name))
        awc_attribute_count++
    }}

    Object object
    int awc_count = 0
    for object in entire(module) do {{
        if (awc_count >= {row_limit}) {{
            awc_emit("TRUNCATED")
            break
        }}
        Buffer awc_row = create
        awc_row += "OBJECT\t" (object."Absolute Number" "") "\t" awc_escape(identifier(object)) "\t" (level(object) "")
        awc_attribute_count = 0
        for awc_attribute in module do {{
            if (!awc_attribute.object) continue
            if (awc_attribute_count >= {attribute_limit}) break
            string awc_attribute_name = awc_attribute.name
            awc_row += "\t" awc_escape(object.awc_attribute_name "")
            awc_attribute_count++
        }}
        awc_emit(stringOf(awc_row))
        delete awc_row
        awc_count++
    }}
    close(module, false)
    awc_ok("EXPORT_MODULE_DONE")
}}
'''.strip()


def check_module(module_path: str, mode: str = "read") -> str:
    """Build DXL that checks whether a module can be opened."""
    return CHECK_TEMPLATE.format(open_statement=open_module(module_path, mode))


def list_objects(module_path: str, attributes: Iterable[str], loop: str, limit: int) -> str:
    """Build bounded DXL that lists module objects."""
    if loop not in {"module", "entire", "all", "document"}:
        raise ValueError("Unsupported DOORS object loop.")
    declarations, fields, _ = attribute_fragments(attributes)
    fields = "".join(f' "\\t" ({field}"")' for field in fields)
    iterable = "module" if loop == "module" else f"{loop}(module)"
    return LIST_TEMPLATE.format(
        open_statement=open_module(module_path, "read"),
        declarations=declarations,
        iterable=iterable,
        limit=int(limit),
        fields=fields,
    )


def get_object(module_path: str, absolute_number: int, attributes: Iterable[str]) -> str:
    """Build DXL that reads one object and selected attributes."""
    declarations, fields, _ = attribute_fragments(attributes)
    fields = "".join(f' "\\t" ({field}"")' for field in fields)
    return GET_TEMPLATE.format(
        open_statement=open_module(module_path, "read"),
        declarations=declarations,
        absolute_number=int(absolute_number),
        fields=fields,
    )


def get_attr(module_path: str, search_text: str, case_sensitive: bool = False) -> str:
    """Build bounded DXL that lists module objects."""
    return GET_ATTR.format(
        open_statement=open_module(module_path, "read"),
        search_text=search_text,
        case_sensitive="true" if case_sensitive else "false"
    )


def export_module(module_path: str, row_limit: int, attribute_limit: int = 50) -> str:
    """Build a bounded read of object attributes and values for import mapping."""

    if not 1 <= int(attribute_limit) <= 50:
        raise ValueError("Unsupported DOORS attribute limit.")
    return EXPORT_MODULE_TEMPLATE.format(
        open_statement=open_module(module_path, "read"),
        row_limit=int(row_limit),
        attribute_limit=int(attribute_limit),
    )
