from pathlib import Path

from .config import RESULT_MODE_APPLICATION, RESULT_MODE_FILE
from .escape import dxl_quote

COMMON_DXL = r'''
string __aw_escape(string value) {
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

void __aw_error(string code, string message) {
    __aw_emit("ERR\t" __aw_escape(code) "\t" __aw_escape(message))
}

void __aw_ok(string message) {
    __aw_emit("OK\t" __aw_escape(message))
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
        return "Buffer __aw_result = create"
    if result_mode != RESULT_MODE_FILE or result_file is None:
        raise ValueError("A result file is required for file result mode.")
    return f'''string __aw_result_file = {dxl_quote(str(result_file))}
Stream __aw_result = write __aw_result_file'''


def build_emitter(result_mode: str) -> str:
    """Build one line emitter for the selected DXL result sink."""
    if result_mode == RESULT_MODE_APPLICATION:
        return '''void __aw_emit(string value) {
    __aw_result += value
    __aw_result += "\\n"
}'''
    if result_mode == RESULT_MODE_FILE:
        return '''void __aw_emit(string value) {
    __aw_result << value << "\\n"
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
    return '''oleSetResult("AW_DOORS_RESULT|" stringOf(__aw_result))
delete __aw_result'''


def file_result_footer() -> str:
    """Return DXL that closes and announces the result file."""
    return '''close __aw_result
oleSetResult("AW_DOORS_OK|" __aw_result_file)
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
