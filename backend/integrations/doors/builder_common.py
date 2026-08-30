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
    awc_emit("ERR\t" awc_escape(code) "\t" awc_escape(message))
}

void awc_ok(string message) {
    awc_emit("OK\t" awc_escape(message))
}
'''.strip()


def wrap_dxl(body: str, result_file: Path | None, result_mode: str) -> str:
    """Wrap DXL with the configured bounded result transport."""
    preamble = build_result_preamble(result_file, result_mode)
    emitter = build_emitter(result_mode)
    footer = build_result_footer(result_file, result_mode)
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
Stream awc_result = write awc_result_file'''


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


def build_result_footer(result_file: Path | None, result_mode: str) -> str:
    """Build the DXL footer for file or Application.Result delivery."""
    if result_mode == RESULT_MODE_APPLICATION:
        return application_result_footer()
    if result_mode != RESULT_MODE_FILE or result_file is None:
        raise ValueError("A result file is required for file result mode.")
    return file_result_footer()


def application_result_footer() -> str:
    """Return DXL that publishes the buffered payload through OLE Result."""
    return '''oleSetResult("AW_DOORS_RESULT|" stringOf(awc_result))
delete awc_result'''


def file_result_footer() -> str:
    """Return DXL that closes and announces the result file."""
    return '''close awc_result
oleSetResult("AW_DOORS_OK|" awc_result_file)
'''.strip()


def open_module(module_path: str, mode: str) -> str:
    """Build an escaped DXL module-open statement."""
    path = dxl_quote(module_path)
    statements = {
        "read": f"Module module = read({path}, false)",
        "edit": f"Module module = edit({path}, false, true)",
        "share": f"Module module = share({path}, false, true)",
    }
    if mode not in statements:
        raise ValueError("Unsupported module mode.")
    return statements[mode]

def attribute_fragments(attributes: Iterable[str]) -> tuple[str, str]:
    """Build safe attribute declarations and output fragments."""
    declarations = []
    objects = []
    variables = []
    for index, attribute in enumerate(attributes):
        variable = f"awc_attribute_{index}"
        declarations.append(f"string {variable} = {dxl_quote(attribute)}")
        objects.append(f'awc_escape(object.{variable})')
        variables.append(variable)
    return "\n".join(declarations), objects, variables


def create_func_declarations(*declarations):
    return "\n".join(declarations)
