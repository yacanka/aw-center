from collections.abc import Iterable

from .builder_common import open_module
from .escape import dxl_quote

CHECK_TEMPLATE = r'''
noError
{open_statement}
string __aw_open_error = lastError
if (!null __aw_open_error || null module) {{
    __aw_error(__aw_output, "OPEN_MODULE", __aw_open_error)
}} else {{
    __aw_ok(__aw_output, "MODULE_OPENED")
    close(module, false)
}}
'''.strip()

LIST_TEMPLATE = r'''
noError
{open_statement}
string __aw_open_error = lastError
if (!null __aw_open_error || null module) {{
    __aw_error(__aw_output, "OPEN_MODULE", __aw_open_error)
}} else {{
    {declarations}
    Object object
    int __aw_count = 0
    for object in {iterable} do {{
        if (__aw_count >= {limit}) break
        __aw_output << "OBJECT" << "\t" << (object."Absolute Number" "")
                    << "\t" << __aw_escape(identifier(object))
                    << "\t" << (level(object) "") {fields} << "\n"
        __aw_count++
    }}
    close(module, false)
    __aw_ok(__aw_output, "LIST_OBJECTS_DONE")
}}
'''.strip()

GET_TEMPLATE = r'''
noError
{open_statement}
string __aw_open_error = lastError
if (!null __aw_open_error || null module) {{
    __aw_error(__aw_output, "OPEN_MODULE", __aw_open_error)
}} else {{
    {declarations}
    Object object = object({absolute_number}, module)
    if (null object) {{
        __aw_error(__aw_output, "OBJECT_NOT_FOUND", "Object was not found")
    }} else {{
        __aw_output << "OBJECT" << "\t" << (object."Absolute Number" "")
                    << "\t" << __aw_escape(identifier(object))
                    << "\t" << (level(object) "") {fields} << "\n"
    }}
    close(module, false)
}}
'''.strip()


def check_module(module_path: str, mode: str = "read") -> str:
    """Build DXL that checks whether a module can be opened."""
    return CHECK_TEMPLATE.format(open_statement=open_module(module_path, mode))


def list_objects(module_path: str, attributes: Iterable[str], loop: str, limit: int) -> str:
    """Build bounded DXL that lists module objects."""
    if loop not in {"module", "entire", "all", "document"}:
        raise ValueError("Unsupported DOORS object loop.")
    declarations, fields = attribute_fragments(attributes)
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
    declarations, fields = attribute_fragments(attributes)
    return GET_TEMPLATE.format(
        open_statement=open_module(module_path, "read"),
        declarations=declarations,
        absolute_number=int(absolute_number),
        fields=fields,
    )


def attribute_fragments(attributes: Iterable[str]) -> tuple[str, str]:
    """Build safe attribute declarations and output fragments."""
    declarations = []
    fields = []
    for index, attribute in enumerate(attributes):
        variable = f"__aw_attribute_{index}"
        declarations.append(f"string {variable} = {dxl_quote(attribute)}")
        fields.append(f' << "\\t" << __aw_escape(object.{variable})')
    return "\n".join(declarations), "".join(fields)
