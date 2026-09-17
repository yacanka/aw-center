"""Shared safe DXL builder primitives."""

from pathlib import Path

from .config import RESULT_MODE_APPLICATION, RESULT_MODE_FILE
from collections.abc import Iterable
from .escape import dxl_quote

COMMON_DXL = r'''
string awc_escape(string value) {
    if (null value) return "\\N"
    Buffer buffer = create
    int index
    for (index = 0; index < length(value); index++) {
        string character = value[index:index]
        if (character == "\\") buffer += "\\\\"
        else if (character == "\n") buffer += "\\n"
        else if (character == "\r") buffer += "\\r"
        else if (character == "\t") buffer += "\\t"
        else buffer += character
    }
    string result = stringOf(buffer)
    delete buffer
    return result
}

void awc_error(string code, string message) {
    // Group the call itself: DXL can include following concatenation in its argument.
    awc_emit("ERR\t" (awc_escape(code)) "\t" awc_escape(message))
}

void awc_ok(string message) {
    awc_emit("OK\t" awc_escape(message))
}
'''.strip()


def wrap_dxl(body: str, result_file: Path | None, result_mode: str, result_token: str = "") -> str:
    """Wrap DXL with the configured bounded result transport."""
    preamble = build_result_preamble(result_file, result_mode)
    emitter = build_emitter(result_mode)
    footer = build_result_footer(result_file, result_mode, result_token)
    return f"""pragma runLim, 0

{preamble}

{emitter}

{COMMON_DXL}

{body}

{footer}
""".strip()


def build_result_preamble(result_file: Path | None, result_mode: str) -> str:
    """Declare the selected DXL result sink before operation execution."""
    if result_mode == RESULT_MODE_APPLICATION:
        return "Buffer awc_result = create"
    if result_mode != RESULT_MODE_FILE or result_file is None:
        raise ValueError("A result file is required for file result mode.")
    return f'''string awc_result_file = {dxl_quote(str(result_file))}
noError
Stream awc_result = write(awc_result_file, CP_UTF8)
string awc_result_error = lastError
if (!null awc_result_error || null awc_result) {{
    oleSetResult("AW_DOORS_ERR|" awc_result_file)
    halt
}}'''


def build_emitter(result_mode: str) -> str:
    """Build one line emitter for the selected DXL result sink."""
    if result_mode == RESULT_MODE_APPLICATION:
        return '''void awc_emit(string value) {
    awc_result += value
    awc_result += "\\n"
}'''
    if result_mode == RESULT_MODE_FILE:
        return '''void awc_emit(string value) {
    awc_result << value << "\\n"
}'''
    raise ValueError("Unsupported DOORS result mode.")


def build_result_footer(result_file: Path | None, result_mode: str, result_token: str = "") -> str:
    """Build the DXL footer for file or Application.Result delivery."""
    if result_mode == RESULT_MODE_APPLICATION:
        return application_result_footer(result_token)
    if result_mode != RESULT_MODE_FILE or result_file is None:
        raise ValueError("A result file is required for file result mode.")
    return file_result_footer()


def application_result_footer(result_token: str = "") -> str:
    """Return DXL that publishes the buffered payload through OLE Result."""
    prefix = "AW_DOORS_RESULT|" + (result_token + "|" if result_token else "")
    return f'''oleSetResult({dxl_quote(prefix)} stringOf(awc_result))
delete awc_result'''


def file_result_footer() -> str:
    """Return DXL that closes and announces the result file."""
    return '''close awc_result
oleSetResult("AW_DOORS_OK|" awc_result_file)
'''.strip()


def open_module(module_path: str, mode: str, *, promote_read: bool = False) -> str:
    """Build an escaped DXL module-open statement."""
    return open_named_module(dxl_quote(module_path), mode, "module", promote_read=promote_read)


def open_named_module(path: str, mode: str, variable: str, *, promote_read: bool = False) -> str:
    """Open a module from a trusted DXL expression while tracking ownership."""
    statements = {
        "read": f"read({path}, false)",
        "edit": f"edit({path}, false, true)",
        "share": f"share({path}, false, true)",
    }
    if mode not in statements:
        raise ValueError("Unsupported module mode.")
    # Missing/inaccessible paths can yield a null ModName_; DOORS raises a
    # runtime error if that handle is passed to open(). Keep read/edit errors
    # attributable to the actual module-open operation instead.
    owned = f'''ModName_ awc_ref_{variable} = module({path})
bool awc_owns_{variable} = true
if (!null awc_ref_{variable}) {{
    awc_owns_{variable} = !open(awc_ref_{variable})
}}'''
    if mode == "read":
        return f"{owned}\nModule {variable} = {statements[mode]}"
    promotion = ""
    if promote_read:
        # Inspect the loaded handle without opening/downgrading an editor's
        # module. Only an existing reader may be promoted by a CRUD write.
        promotion = f'''
bool awc_restore_{variable} = false
bool awc_display_{variable} = false
if (!awc_owns_{variable}) {{
    Module awc_existing_{variable} = data(moduleVersion(awc_ref_{variable}))
    if (!null awc_existing_{variable} && isRead(awc_existing_{variable})) {{
        awc_restore_{variable} = true
        awc_display_{variable} = isVisible(awc_existing_{variable})
        awc_owns_{variable} = true
    }}
}}'''
    rejection = (
        "Close the module's existing edit or shared session before submitting a write"
        if promote_read else "Close the module in the desktop client before submitting a write"
    )
    return f'''{owned}
{promotion}
Module {variable} = null
if (awc_owns_{variable}) {{
    {variable} = {statements[mode]}
}} else {{
    awc_error("MODULE_ALREADY_OPEN", "{rejection}")
}}'''

def attribute_fragments(attributes: Iterable[str]) -> tuple[str, list[str], list[str]]:
    """Build safe attribute declarations and output fragments."""
    declarations = []
    objects = []
    variables = []
    for index, attribute in enumerate(attributes):
        variable = f"awc_attribute_{index}"
        declarations.append(f"string {variable} = {dxl_quote(attribute)}")
        objects.append(f'awc_escape(object.{variable} "")')
        variables.append(variable)
    return "\n".join(declarations), objects, variables


def create_func_declarations(*declarations):
    return "\n".join(declarations)
