from typing import Any

from .builder_common import open_module
from .escape import dxl_quote, dxl_value

UPDATE_TEMPLATE = r'''
noError
{open_statement}
string __aw_open_error = lastError
if (!null __aw_open_error || null module) {{
    __aw_error(__aw_output, "OPEN_MODULE_EDIT", __aw_open_error)
}} else {{
    Object object = object({absolute_number}, module)
    if (null object) {{
        __aw_error(__aw_output, "OBJECT_NOT_FOUND", "Object was not found")
        close(module, false)
    }} else {{
        bool __aw_has_error = false
        {assignments}
        if (!__aw_has_error) {{
            save(module)
            __aw_ok(__aw_output, "ATTRIBUTES_SAVED")
        }}
        close(module, false)
    }}
}}
'''.strip()

CREATE_TEMPLATE = r'''
noError
{open_statement}
string __aw_open_error = lastError
if (!null __aw_open_error || null module) {{
    __aw_error(__aw_output, "OPEN_MODULE_EDIT", __aw_open_error)
}} else {{
    {lookup}
    noError
    {creation}
    string __aw_create_error = lastError
    if (!null __aw_create_error || null created) {{
        __aw_error(__aw_output, "CREATE_OBJECT", __aw_create_error)
    }} else {{
        bool __aw_has_error = false
        {assignments}
        if (!__aw_has_error) {{
            save(module)
            __aw_output << "CREATED" << "\t" << (created."Absolute Number" "")
                        << "\t" << __aw_escape(identifier(created))
                        << "\t" << (level(created) "") << "\n"
            __aw_ok(__aw_output, "OBJECT_CREATED")
        }}
    }}
    close(module, false)
}}
'''.strip()

RELATIVE_TEMPLATE = r'''
Object relative = object({absolute_number}, module)
if (null relative) {{
    __aw_error(__aw_output, "BASE_OBJECT_NOT_FOUND", "Relative object was not found")
    close(module, false)
    halt
}}
'''.strip()

ASSIGNMENT_TEMPLATE = r'''
string {variable} = {attribute_name}
noError
{object_name}.{variable} = {attribute_value}
string {error_variable} = lastError
if (!null {error_variable}) {{
    __aw_error(__aw_output, "SET_ATTRIBUTE", {attribute_name} " : " {error_variable})
    __aw_has_error = true
}}
'''.strip()


def set_object_attributes(module_path: str, absolute_number: int, attributes) -> str:
    """Build transactional DXL that updates object attributes."""
    if not attributes:
        raise ValueError("attributes cannot be empty.")
    return UPDATE_TEMPLATE.format(
        open_statement=open_module(module_path, "edit"),
        absolute_number=int(absolute_number),
        assignments=build_assignments(attributes, "object", "update"),
    )


def create_object(module_path: str, position: str, relative_number, attributes) -> str:
    """Build transactional DXL that creates a module object."""
    lookup, creation = create_fragments(position, relative_number)
    return CREATE_TEMPLATE.format(
        open_statement=open_module(module_path, "edit"),
        lookup=lookup,
        creation=creation,
        assignments=build_assignments(attributes, "created", "create"),
    )


def create_fragments(position: str, relative_number: int | None) -> tuple[str, str]:
    """Return safe lookup and creation DXL fragments."""
    if position == "first":
        return "", "Object created = create(module)"
    if position not in {"after", "before", "below", "below_last"}:
        raise ValueError("Unsupported object creation position.")
    if relative_number is None:
        raise ValueError("relative_absolute_number is required.")
    statements = {
        "after": "Object created = create after relative",
        "before": "Object created = create before relative",
        "below": "Object created = create below relative",
        "below_last": "Object created = create last below relative",
    }
    return relative_lookup(relative_number), statements[position]


def relative_lookup(absolute_number: int) -> str:
    """Build DXL that resolves a required relative object."""
    return RELATIVE_TEMPLATE.format(absolute_number=int(absolute_number))


def build_assignments(attributes: dict[str, Any], object_name: str, prefix: str) -> str:
    """Build escaped scalar attribute assignments."""
    return "\n".join(
        assignment(index, name, value, object_name, prefix)
        for index, (name, value) in enumerate(attributes.items())
    )


def assignment(index: int, name: str, value: Any, object_name: str, prefix: str) -> str:
    """Build one checked DXL attribute assignment."""
    variable = f"__aw_{prefix}_attribute_{index}"
    error_variable = f"__aw_set_error_{prefix}_{index}"
    return ASSIGNMENT_TEMPLATE.format(
        variable=variable,
        attribute_name=dxl_quote(name),
        object_name=object_name,
        attribute_value=dxl_value(value),
        error_variable=error_variable,
    )
